def fields(field):
    result = [field("AIHUB_DOCUMENT_MODELS", "文档模型顺序", "各 Skill 模型", "list", default=[],
                    help="只影响对应 Skill；留空沿用按任务选择模型的现有行为，填写准确模型 ID。")]
    return result
