from importlib import import_module


def fields(field):
    result = [field("AIHUB_AUDIO_MODELS", "音频模型顺序", "各 Skill 模型", "list", default=[],
                    help="只影响对应 Skill；留空沿用按任务选择模型的现有行为，填写准确模型 ID。")]
    result.extend(import_module(__package__ + '.models.minimax-speech.configuration').fields(field))
    return result
