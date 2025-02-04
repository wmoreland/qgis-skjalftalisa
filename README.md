# QGIS-Skjálftalísa
A plugin for loading earthquake data into QGIS.

https://github.com/user-attachments/assets/3fc6eec2-c1df-442d-ade5-e8c22fbab336

# How to install

1. Download a zip archive of the latest release from [here](https://github.com/wmoreland/qgis-skjalftalisa/releases/latest)

2. In QGIS, from the "Plugins" menu, open "Manage and Install Plugins...". On the "Install from ZIP" tab, browse to the downloaded zip archive and click "Install Plugin". A message may appear warning you about installing plugins from untrusted sources. Press "Yes" to continue.

3. The plugin is now installed. However, the geopandas python library is required for the plugin to work. From the "Plugins" menu, open the python console. Insert the following two lines into the console to install geopandas using pip:

`import pip`

`pip.main(['install', 'geopandas'])`

4. The plugin should now be completely installed and working. Enjoy!
