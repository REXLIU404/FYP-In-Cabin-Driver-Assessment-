"""``ApiTap`` (e2e_support.py) without a browser: a fake Playwright route is enough to check what the
tap records. Deferred minor M6: with ``drop_images`` a REWRITTEN request must keep saying what the
SERVER received (``sent_body``), not fall back to the browser's own body."""
import json

from e2e_support import ApiTap


class FakeResponse:
    status, ok = 201, True

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class FakeRequest:
    def __init__(self, body, attempt="1"):
        self.post_data = json.dumps(body)
        self.headers = {"x-attempt-index": attempt}


class FakeRoute:
    def __init__(self, body):
        self.request = FakeRequest(body)
        self.fetched_with = "not fetched"
        self.fulfilled = None

    def fetch(self, post_data=None):
        self.fetched_with = post_data
        return FakeResponse({"window_id": 1})

    def fulfill(self, response):
        self.fulfilled = response


BROWSER_BODY = {"request_id": "r1", "image_base64": "AAAA", "telemetry_seq": 4}


def test_a_rewritten_request_keeps_what_the_server_got_after_the_picture_is_dropped():
    tap = ApiTap()
    tap.drop_images = True
    tap.rewrite_infer = lambda body: {**body, "image_base64": None, "telemetry_seq": 99}
    route = FakeRoute(BROWSER_BODY)
    tap._infer(route, "s1")
    call = tap.infer[0]
    assert json.loads(route.fetched_with)["telemetry_seq"] == 99  # the server got the rewrite
    assert call.sent_body["image_base64"] is None and call.sent_body["telemetry_seq"] == 99
    assert tap.answered_with_image() == []  # the server received no picture
    assert call.body["image_base64"] == "<dropped>" and call.raw == ""  # the browser's frame is not kept


def test_an_unrewritten_request_drops_the_picture_and_still_counts_as_one_with_an_image():
    tap = ApiTap()
    tap.drop_images = True
    tap._infer(FakeRoute(BROWSER_BODY), "s1")
    call = tap.infer[0]
    assert call.sent_body["image_base64"] == "<dropped>" and call.sent_body["telemetry_seq"] == 4
    assert tap.answered_with_image() == [call]
    assert len(call.raw) == 0 and call.sent_raw is None


def test_a_dropped_rewritten_body_stays_compact():
    tap = ApiTap()
    tap.drop_images = True
    tap.rewrite_infer = lambda body: dict(body)  # keeps the picture
    tap._infer(FakeRoute(BROWSER_BODY), "s1")
    call = tap.infer[0]
    assert "AAAA" not in call.sent_raw and call.sent_body["image_base64"] == "<dropped>"
