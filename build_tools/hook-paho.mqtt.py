# PyInstaller hook for paho-mqtt
# Ensures all paho.mqtt submodules are included

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all paho.mqtt submodules
hiddenimports = collect_submodules('paho.mqtt')

# Collect any data files if present
datas = collect_data_files('paho.mqtt')
