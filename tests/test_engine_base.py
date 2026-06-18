from mflux_server.engines.base import GenerationRequest


def test_defaults_keep_text_to_image_fields():
    req = GenerationRequest(model="m", prompt="p")
    assert req.init_image is None
    assert req.image_strength is None
    assert req.negative_prompt is None


def test_img2img_fields_settable():
    req = GenerationRequest(model="m", prompt="p", init_image=b"PNG",
                            image_strength=0.6, negative_prompt="blurry")
    assert req.init_image == b"PNG"
    assert req.image_strength == 0.6
    assert req.negative_prompt == "blurry"
