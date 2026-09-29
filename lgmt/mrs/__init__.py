from .equivalence import (
    MRE11,
    MRE12,
    MRE13,
    MRE14,
    MRE15,
    MRE16,
    MRE21,
    MRE22,
    MRE23,
    MRE24,
)
from .symbol import MRS1, MRS2
from .premise import MRP1, MRP2, MRP3, MRP4, MRP5
from .conclusion import MRC1, MRC2, MRC3

__all__ = [
    "MRS1",
    "MRS2",
    "MRP1",
    "MRP2",
    "MRP3",
    "MRP4",
    "MRP5",
    "MRC1",
    "MRC2",
    "MRC3",
    "MRE11",
    "MRE12",
    "MRE13",
    "MRE14",
    "MRE15",
    "MRE16",
    "MRE21",
    "MRE22",
    "MRE23",
    "MRE24",
]

#: All 20 metamorphic relations, instantiated.
ALL_MRS = [globals()[name]() for name in __all__]

#: Registry mapping MR index (e.g. "MR-E1.5") to the relation instance.
MR_INDEX_REGISTRY = {mr.index: mr for mr in ALL_MRS}

#: Registry mapping MR class name (e.g. "MRE15") to the MR *class*.
MR_CLASS_REGISTRY = {name: globals()[name] for name in __all__}


def get_mr(name_or_index: str):
    """Resolve an MR instance by class name (``MRE15``) or index (``MR-E1.5``)."""
    key = name_or_index.strip()
    if key in MR_CLASS_REGISTRY:
        return MR_CLASS_REGISTRY[key]()
    if key in MR_INDEX_REGISTRY:
        return MR_INDEX_REGISTRY[key]
    # allow fuzzy match, e.g. "E15" or "mre15"
    norm = key.upper().replace("MR-", "").replace("MR", "")
    for cls_name, cls in MR_CLASS_REGISTRY.items():
        if cls_name.upper().replace("MR", "") == norm:
            return cls()
    for idx, mr in MR_INDEX_REGISTRY.items():
        if idx.upper().replace("MR-", "") == norm:
            return mr
    raise KeyError(f"Unknown MR: {name_or_index!r}")
