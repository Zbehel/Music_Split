"""Stem configuration for all models"""

STEM_CONFIGS = {
    "htdemucs_6s": {
        "name": "6-Stem Separation (HD)",
        "description": "Vocals, Drums, Bass, Other, Guitar, Piano",
        "stems": ["drums", "bass", "other", "vocals", "guitar", "piano"],
        "desc": "6 stems complet",
        "emoji": [ "🥁", "🎸", "🎼", "🎤","🎹", "📻"],
    },
    "htdemucs_ft": {
        "name": "4-Stem Separation (Fast)",
        "description": "Vocals, Drums, Bass, Other",
        "stems": ["drums", "bass", "other","vocals"],
        "desc": "4 stems haute qualité",
        "emoji": ["🥁", "🎸", "🎼", "🎤"],
    },
    "mvsep_full": {
        "name": "MVSEP Full",
        "description": "Vocals, Drums, Bass, Other",
        "stems": ["drums", "bass", "other","vocals"],
        "desc": "4 stems complet",
        "emoji": ["🥁", "🎸", "🎼", "🎤"],
    },
}

# Helper functions
def get_stems(model_name: str) -> list:
    """Get stem list for model"""
    if model_name not in STEM_CONFIGS:
        raise ValueError(f"Unknown model: {model_name}")
    return STEM_CONFIGS[model_name]["stems"]

def get_stem_emoji(model_name: str, stem_index: int) -> str:
    """Get emoji for specific stem"""
    stems = STEM_CONFIGS[model_name]["stems"]
    if stem_index >= len(stems):
        return "🎵"
    emoji_list = STEM_CONFIGS[model_name].get("emoji", ["🎵"] * len(stems))
    return emoji_list[stem_index]

def get_num_stems(model_name: str) -> int:
    """Get number of stems for model"""
    return len(STEM_CONFIGS[model_name]["stems"])

def get_max_stems() -> int:
    """Get maximum stems across all models."""
    return max(len(config["stems"]) for config in STEM_CONFIGS.values())
