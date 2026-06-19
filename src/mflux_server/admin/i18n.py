SUPPORTED = ("en", "zh")

STRINGS = {
    "nav_dashboard": {"en": "Dashboard", "zh": "仪表盘"},
    "nav_models": {"en": "Models", "zh": "模型"},
    "nav_gallery": {"en": "Gallery", "zh": "画廊"},
    "nav_generate": {"en": "Generate", "zh": "生成"},
    "nav_settings": {"en": "Settings", "zh": "设置"},
    "nav_logout": {"en": "Log out", "zh": "登出"},
    "lang_en": {"en": "EN", "zh": "EN"},
    "lang_zh": {"en": "中文", "zh": "中文"},

    "login_title": {"en": "Sign in", "zh": "登录"},
    "login_placeholder": {"en": "Admin password", "zh": "管理密码"},
    "login_button": {"en": "Sign in", "zh": "登录"},
    "login_error": {"en": "Wrong password", "zh": "密码错误"},

    "dashboard_title": {"en": "Dashboard", "zh": "仪表盘"},
    "st_running": {"en": "Running", "zh": "运行中"},
    "st_queued": {"en": "Queued", "zh": "队列等待"},
    "st_done": {"en": "Completed", "zh": "已完成"},
    "st_history": {"en": "Images", "zh": "历史图片"},
    "st_idle": {"en": "Queue idle", "zh": "队列空闲"},
    "col_task": {"en": "Job", "zh": "任务"},
    "col_status": {"en": "Status", "zh": "状态"},
    "col_model": {"en": "Model", "zh": "模型"},
    "col_prompt": {"en": "Prompt", "zh": "提示词"},

    "models_title": {"en": "Model management", "zh": "模型管理"},
    "col_name": {"en": "Name", "zh": "名称"},
    "col_family": {"en": "Family", "zh": "家族"},
    "col_size": {"en": "Size", "zh": "大小"},
    "col_actions": {"en": "Actions", "zh": "操作"},
    "tag_default": {"en": "default", "zh": "默认"},
    "downloaded": {"en": "Downloaded", "zh": "已下载"},
    "not_downloaded": {"en": "Not downloaded", "zh": "未下载"},
    "btn_download": {"en": "Download", "zh": "下载"},
    "btn_set_default": {"en": "Set default", "zh": "设为默认"},
    "btn_delete": {"en": "Delete", "zh": "删除"},
    "confirm_delete_model": {"en": "Delete local weights for this model?", "zh": "确认删除该模型的本地权重？"},
    "models_hint": {"en": "Downloads run in the background; refresh to see status.",
                     "zh": "下载为后台任务；刷新本页查看最新状态。"},
    "download_by_url": {"en": "Download from HuggingFace", "zh": "从 HuggingFace 下载"},
    "download_url_hint": {"en": "Paste a HuggingFace URL or org/model id. This caches the weights to disk; a model is usable for generation only if the engine supports it.",
                           "zh": "粘贴 HuggingFace 链接或 org/model。下载只是把权重缓存到磁盘；模型能否用于生成取决于引擎是否支持。"},
    "cached_models": {"en": "Downloaded (cache)", "zh": "已下载（缓存）"},
    "cached_empty": {"en": "Nothing downloaded yet.", "zh": "还没有下载任何模型。"},
    "downloading": {"en": "Downloading", "zh": "下载中"},
    "download_done": {"en": "Downloaded", "zh": "下载完成"},
    "refresh_list": {"en": "refresh list", "zh": "刷新列表"},

    "gallery_title": {"en": "Gallery / History", "zh": "画廊 / 历史"},
    "gallery_empty": {"en": "No generations yet.", "zh": "还没有生成记录。"},
    "btn_regenerate": {"en": "Re-generate", "zh": "重新生成"},
    "btn_download_file": {"en": "Download", "zh": "下载"},
    "confirm_delete_image": {"en": "Delete this image?", "zh": "删除这张？"},
    "hist_size": {"en": "Size", "zh": "尺寸"},
    "hist_steps": {"en": "Steps", "zh": "步数"},
    "hist_seed": {"en": "Seed", "zh": "种子"},
    "hist_guidance": {"en": "Guidance", "zh": "引导"},
    "hist_strength": {"en": "Strength", "zh": "强度"},
    "hist_time": {"en": "Time", "zh": "耗时"},

    "settings_title": {"en": "Settings", "zh": "设置"},
    "settings_apikey": {"en": "API Key", "zh": "API Key"},
    "btn_reset_key": {"en": "Reset key", "zh": "重置 Key"},
    "confirm_reset_key": {"en": "The old key stops working immediately. Continue?",
                           "zh": "重置后旧 Key 立即失效，确认？"},
    "settings_sdk_hint": {"en": "In the OpenAI SDK use this key with",
                           "zh": "在 OpenAI SDK 里用此 Key 搭配"},
    "settings_defaults": {"en": "Generation defaults", "zh": "生成默认"},
    "lbl_default_model": {"en": "Default model", "zh": "默认模型"},
    "lbl_default_steps": {"en": "Default steps", "zh": "默认步数"},
    "lbl_bind": {"en": "Bind address", "zh": "监听地址"},
    "lbl_output": {"en": "Output dir", "zh": "输出目录"},

    "generate_title": {"en": "Generate", "zh": "生成"},
    "lbl_prompt": {"en": "Prompt", "zh": "提示词"},
    "lbl_model": {"en": "Model", "zh": "模型"},
    "lbl_size": {"en": "Size", "zh": "尺寸"},
    "lbl_steps": {"en": "Steps (optional)", "zh": "步数（可选）"},
    "lbl_seed": {"en": "Seed (optional)", "zh": "种子（可选）"},
    "lbl_negative": {"en": "Negative prompt (optional)", "zh": "反向提示词（可选）"},
    "lbl_image": {"en": "Source image", "zh": "源图"},
    "lbl_strength": {"en": "Strength", "zh": "强度"},
    "btn_generate": {"en": "Generate", "zh": "生成"},
    "generating": {"en": "Generating…", "zh": "生成中…"},
    "generate_failed": {"en": "Generation failed", "zh": "生成失败"},
    "tab_t2i": {"en": "Text-to-image", "zh": "文生图"},
    "tab_img2img": {"en": "Image-to-image", "zh": "图生图"},
    "no_img2img_models": {"en": "No image-to-image models installed yet.",
                           "zh": "还没有支持图生图的模型。"},
}


def get_lang(request) -> str:
    lang = request.cookies.get("lang", "en")
    return lang if lang in SUPPORTED else "en"


def translate(lang: str, key: str) -> str:
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key


def i18n_context(request) -> dict:
    lang = get_lang(request)
    return {"lang": lang, "t": lambda key: translate(lang, key)}
