from flask import Flask, render_template, request, make_response, g, jsonify
from redis import Redis
from redis.exceptions import RedisError
import importlib.util
import os
import re
import socket
import random
import json
import logging

option_a = os.getenv('OPTION_A', "Cats")
option_b = os.getenv('OPTION_B', "Dogs")
hostname = socket.gethostname()

app = Flask(__name__)

gunicorn_error_logger = logging.getLogger('gunicorn.error')
app.logger.handlers.extend(gunicorn_error_logger.handlers)
app.logger.setLevel(logging.INFO)

def get_redis():
    if not hasattr(g, 'redis'):
        g.redis = Redis(host="redis", db=0, socket_timeout=5)
    return g.redis

@app.route("/", methods=['POST','GET'])
def hello():
    voter_id = request.cookies.get('voter_id')
    if not voter_id:
        voter_id = hex(random.getrandbits(64))[2:-1]

    vote = None

    if request.method == 'POST':
        redis = get_redis()
        vote = request.form['vote']
        app.logger.info('Received vote for %s', vote)
        data = json.dumps({'voter_id': voter_id, 'vote': vote})
        redis.rpush('votes', data)

    resp = make_response(render_template(
        'index.html',
        option_a=option_a,
        option_b=option_b,
        hostname=hostname,
        vote=vote,
    ))
    resp.set_cookie('voter_id', voter_id)
    return resp


@app.get("/api/options")
def api_options():
    return jsonify({"a": option_a, "b": option_b})


FEATURE_NAME = re.compile(r'^[a-z][a-z0-9_]{0,31}$')
FEATURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'regression_features')


def regression_error(status, error):
    return jsonify({"error": error, "service": "vote"}), status


def load_regression_feature(name):
    if not FEATURE_NAME.fullmatch(name):
        return None, regression_error(400, "invalid_feature")
    feature_path = os.path.realpath(os.path.join(FEATURES_DIR, name + ".py"))
    if os.path.dirname(feature_path) != os.path.realpath(FEATURES_DIR):
        return None, regression_error(400, "invalid_feature")
    if not os.path.isfile(feature_path):
        return None, regression_error(404, "feature_not_found")
    module_name = "regression_features." + name
    spec = importlib.util.spec_from_file_location(module_name, feature_path)
    if spec is None or spec.loader is None:
        return None, regression_error(404, "feature_not_found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evaluate = getattr(module, "evaluate", None)
    if not callable(evaluate):
        raise TypeError("feature evaluate is not callable")
    return evaluate, None


@app.get("/api/regression/<name>")
def api_regression(name):
    raw_value = request.args.get("x", None)
    if raw_value is None or not re.fullmatch(r'-?\d+', raw_value):
        return regression_error(400, "invalid_integer")
    try:
        evaluate, error = load_regression_feature(name)
    except Exception:
        app.logger.error("Regression feature failed feature=%s code=feature_failed", name)
        return regression_error(500, "feature_failed")
    if error is not None:
        return error
    try:
        payload = evaluate(int(raw_value))
    except Exception:
        app.logger.error("Regression feature failed feature=%s code=feature_failed", name)
        return regression_error(500, "feature_failed")
    if not isinstance(payload, dict):
        app.logger.error("Regression feature failed feature=%s code=feature_failed", name)
        return regression_error(500, "feature_failed")
    return jsonify(payload)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80, debug=True, threaded=True)


@app.get("/healthz")
def healthz():
    try:
        get_redis().ping()
    except RedisError:
        app.logger.exception("Redis readiness check failed")
        return {"status": "unavailable", "service": "vote"}, 503
    return {"status": "ok", "service": "vote"}
