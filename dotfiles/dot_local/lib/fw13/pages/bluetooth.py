from .common import placeholder


def build():
    return placeholder("Bluetooth", "Bluetooth devices arrive in the next stage. Until then use the bar's Bluetooth "
                       "icon, or:", "Bluetooth devices…", ["blueman-manager"])
