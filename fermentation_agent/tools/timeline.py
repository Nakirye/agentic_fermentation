from datetime import datetime

from fermentation_agent.models import FermentationPhase, Timeline


def build_timeline(
    target_time: datetime,
    phases: list[FermentationPhase],
    autolyse_min: int = 30,
    knead_min: int = 15,
    stretch_fold_count: int = 3,
    stretch_fold_interval_min: int = 30,
    preheat_min: int = 45,
) -> Timeline:
    """Schedule backwards from target_time (= pizzas go into the oven).

    Order (forwards): autolyse → knead → stretch & folds → bulk phases → balling
    → final proof phase(s) → preheat (overlaps final proof) → bake.
    The stretch & folds happen during the first bulk phase.
    """
    raise NotImplementedError
