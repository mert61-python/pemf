# PyInstaller hook for paho-mqtt
# Ensures all paho.mqtt submodules are included

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect all paho.mqtt submodules
hiddenimports = collect_submodules('paho.mqtt')

# Collect any data files if present
datas = collect_data_files('paho.mqtt')
