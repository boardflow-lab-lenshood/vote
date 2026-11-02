from flask import Flask, Response, render_template, request, make_response, g, jsonify
from redis import Redis
from redis.exceptions import RedisError
import importlib.util
import os
import re
import socket
import random
import json
import logging

option_a = os.getenv('OPTION_A', "猫派")
option_b = os.getenv('OPTION_B', "狗派")
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

    vote = request.cookies.get('vote')
    if vote not in ('a', 'b'):
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
    if vote in ('a', 'b'):
        resp.set_cookie('vote', vote)
    return resp


TRACE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,63}')


@app.post("/api/arena/seven-20261103/votes")
def api_arena_seven_votes() -> tuple[Response, int]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_json_object"}), 400

    voter_id = payload.get("voter_id")
    vote = payload.get("vote")
    trace_id = payload.get("trace_id")
    if (
        not isinstance(voter_id, str)
        or not 1 <= len(voter_id) <= 255
        or not voter_id.strip()
        or '\x00' in voter_id
    ):
        return jsonify({"error": "invalid_voter_id"}), 400
    if not isinstance(vote, str) or vote not in ('a', 'b'):
        return jsonify({"error": "invalid_vote"}), 400
    if not isinstance(trace_id, str) or TRACE_ID.fullmatch(trace_id) is None:
        return jsonify({"error": "invalid_trace_id"}), 400

    message = {"voter_id": voter_id, "vote": vote, "trace_id": trace_id}
    try:
        get_redis().rpush('votes', json.dumps(message))
    except RedisError:
        app.logger.exception("Tracked vote enqueue failed")
        return jsonify({"error": "queue_unavailable"}), 503
    return jsonify({"accepted": True, **message}), 202


@app.get("/api/options")
def api_options():
    return jsonify({"a": option_a, "b": option_b})


@app.get("/api/arena/three-20261102/options-metadata")
@app.get("/api/arena/20261102/options-metadata")
def api_arena_options_metadata() -> Response:
    return jsonify({
        "service": "vote",
        "option_count": 2,
        "options": [
            {"id": "a", "label": option_a},
            {"id": "b", "label": option_b},
        ],
    })


@app.get("/api/uat/poll-info")
def api_uat_poll_info():
    return jsonify({
        "title": f"{option_a} vs {option_b}!",
        "options": [
            {"id": "a", "label": option_a},
            {"id": "b", "label": option_b},
        ],
        "option_count": 2,
    })


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
