"""Temporary observation wrapper; imports the unchanged application."""
import json, base64, hashlib, io
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageStat
from app.main import app as original_app

trace = Path('/Users/liu/.codex/worktrees/d39a/FYP-In-Cabin-Driver-Assessment--1/docs/fyp2/evidence/2026-10-12-browser/frame_hash_trace.jsonl')

async def app(scope, receive, send):
    if scope['type'] != 'http' or scope.get('method') != 'POST' or not scope.get('path','').endswith('/infer'):
        return await original_app(scope, receive, send)
    messages, body = [], b''
    while True:
        message = await receive()
        messages.append(message)
        body += message.get('body', b'')
        if not message.get('more_body', False):
            break
    row = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'path':scope['path']}
    try:
        data = json.loads(body)
        row.update(request_id=data.get('request_id'), captured_at=data.get('captured_at'))
        encoded = data.get('image_base64')
        if encoded:
            raw = base64.b64decode(encoded.split(',',1)[-1])
            row['image_sha256'] = hashlib.sha256(raw).hexdigest()
            with Image.open(io.BytesIO(raw)) as image:
                row['dimensions'] = image.size
                stat = ImageStat.Stat(image.convert('RGB').resize((32,32)))
                row['rgb_mean'] = stat.mean
                row['rgb_stddev'] = stat.stddev
    except Exception as exc:
        row['observation_error'] = type(exc).__name__
    iterator = iter(messages)
    async def replay():
        try:
            return next(iterator)
        except StopIteration:
            return await receive()
    response = bytearray()
    async def observe_send(message):
        if message['type'] == 'http.response.start':
            row['status'] = message['status']
        if message['type'] == 'http.response.body':
            response.extend(message.get('body', b''))
        await send(message)
    try:
        await original_app(scope, replay, observe_send)
        result = json.loads(response)
        row['window_id'] = result.get('window_id')
        row['vision_raw'] = result.get('provenance',{}).get('P_distraction_raw')
        row['visual_probabilities'] = result.get('visual_top_classes',[])
    finally:
        with trace.open('a') as stream:
            stream.write(json.dumps(row) + '\n')
