from .common import placeholder


def build():
    return placeholder("Network", "Wi-Fi and Ethernet settings arrive in the next stage. Until then use the bar's "
                       "Wi-Fi icon, or the full editor:", "Network connections…", ["nm-connection-editor"])
