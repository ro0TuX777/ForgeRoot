from forgecompliance.plugins.nz_government import NZGovernmentPlugin
from forgecompliance.plugins.nz_health import NZHealthPlugin
from forgecompliance.plugins.nz_finance import NZFinancePlugin
from forgecompliance.plugins.au_finance import AUFinancePlugin
from forgecompliance.plugins.generic_soc2 import GenericSOC2Plugin
from forgecompliance.plugins.generic_iso27001 import GenericISO27001Plugin
from forgecompliance.plugins.generic_nist import GenericNISTPlugin

ALL_PLUGINS = [
    NZGovernmentPlugin(),
    NZHealthPlugin(),
    NZFinancePlugin(),
    AUFinancePlugin(),
    GenericSOC2Plugin(),
    GenericISO27001Plugin(),
    GenericNISTPlugin(),
]

__all__ = [
    "NZGovernmentPlugin",
    "NZHealthPlugin",
    "NZFinancePlugin",
    "AUFinancePlugin",
    "GenericSOC2Plugin",
    "GenericISO27001Plugin",
    "GenericNISTPlugin",
    "ALL_PLUGINS",
]
