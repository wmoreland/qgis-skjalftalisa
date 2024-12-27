# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QgisSkjalftalisaDockWidget
                                 A QGIS plugin
 Interface for Veðurstofan earthquake data
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2024-12-19
        git sha              : $Format:%H$
        copyright            : (C) 2024 by William M. Moreland
        email                : william@moreland.is
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
import math
import json
import requests
import geopandas as gpd
from datetime import datetime, timedelta

from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import pyqtSignal, QDateTime, Qt
from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsSymbol,
    QgsGraduatedSymbolRenderer,
    QgsRendererRange,
    QgsSymbolLayer,
    QgsProperty,
    QgsStyle,
    QgsSimpleMarkerSymbolLayer,
    QgsSingleSymbolRenderer,
)

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "qgis_skjalfalisa_dockwidget_base.ui")
)


class QgisSkjalftalisaDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, iface, parent=None):
        """Constructor."""
        super(QgisSkjalftalisaDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://doc.qt.io/qt-5/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        # Set flag for time range adjustments
        self.updating_time_range = False

        # Store the iface object
        self.iface = iface

        # Populate the timeComboBox
        self.timeComboBox.addItems(
            [
                "Choose period",
                "Last 1 hour",
                "Last 3 hours",
                "Last 6 hours",
                "Last 12 hours",
                "Last 24 hours",
                "Last 2 days",
                "Last 7 days",
                "Last 14 days",
                "Last 30 days",
                "Last 60 days",
                "Last 90 days",
                "Last 365 days",
            ]
        )
        self.timeComboBox.setCurrentIndex(0)  # Set the placeholder as the default
        self.timeComboBox.currentIndexChanged.connect(self.update_time_range)

        # Set initial values for dateUntilTimeEdit and dateFromTimeEdit
        self.update_time_range()

        # Connect date/time edits to a custom range handler
        self.dateFromTimeEdit.dateTimeChanged.connect(self.handle_custom_date_change)
        self.dateUntilTimeEdit.dateTimeChanged.connect(self.handle_custom_date_change)

        # Initialize variables
        self.loaded_layer = None

        # Initialize areaComboBox
        self.populate_area_combobox()

        # Connect buttons to methods
        self.filterPushButton.clicked.connect(self.fetch_and_load_earthquakes)
        self.resetPushButton.clicked.connect(self.reset_values)

        # Initialize areaCheckBox (optional logic)
        self.areaCheckBox.stateChanged.connect(self.handle_area_checkbox)

    def fetch_and_load_earthquakes(self):
        """Fetch earthquake data and load it into QGIS."""
        start_time = self.dateFromTimeEdit.dateTime()
        end_time = self.dateUntilTimeEdit.dateTime()

        if start_time >= end_time:
            self.show_error(
                "Invalid date range: 'From' time must be earlier than 'Until' time."
            )
            return

        start_time_str = start_time.toString("yyyy-MM-dd HH:mm:ss")
        end_time_str = end_time.toString("yyyy-MM-dd HH:mm:ss")
        size_min = self.magMinSpinBox.value()
        size_max = self.magMaxSpinBox.value()
        depth_min = self.depthMinSpinBox.value()
        depth_max = self.depthMaxSpinBox.value()

        # Include the selected area polygon
        selected_area = self.areaComboBox.currentText()
        if selected_area != "Choose area":
            area_polygon = self.feature_collection_gdf.loc[
                self.feature_collection_gdf["name"] == selected_area
            ]["geometry"].to_json()
            area_polygon = json.loads(area_polygon)["features"][0]["geometry"][
                "coordinates"
            ][0]
            area_polygon = [
                list(coord_xy)
                for coord_xy in [
                    (coord_yx[1], coord_yx[0]) for coord_yx in area_polygon
                ]
            ]
        else:
            area_polygon = None

        body = {
            "depth_max": depth_max,
            "depth_min": depth_min,
            "end_time": end_time_str,
            "event_type": ["qu"],
            "magnitude_preference": ["Mlw"],
            "originating_system": ["SIL picks"],
            "size_max": size_max,
            "size_min": size_min,
            "start_time": start_time_str,
        }

        # Add area if available
        if area_polygon:
            body["area"] = area_polygon

        try:
            # Fetch earthquake data
            response = requests.post(
                "https://vi-api.vedur.is/skjalftalisa/v1/quakefilter", json=body
            )
            if response.status_code == 200:
                quake_data = response.json()
                geojson_data = {
                    "type": "FeatureCollection",
                    "features": quake_data,
                }

                from tempfile import NamedTemporaryFile

                with NamedTemporaryFile(suffix=".geojson", delete=False) as temp_file:
                    geojson_path = temp_file.name
                    with open(geojson_path, "w") as file:
                        json.dump(geojson_data, file, indent=2)

                # Load the earthquake GeoJSON layer
                self.load_geojson_layer(geojson_path, "Earthquakes")

                # Optionally display the area polygon if the checkbox is checked
                if self.areaCheckBox.isChecked() and area_polygon:
                    self.display_area_polygon(selected_area, area_polygon)
            else:
                self.show_error(f"Error: {response.status_code} - {response.text}")
        except Exception as e:
            self.show_error(f"An error occurred: {str(e)}")

    def load_geojson_layer(self, geojson_path, layer_name="Earthquakes"):
        """Load a GeoJSON file as a temporary layer in QGIS, including the date range in the name."""
        # Read the GeoJSON file to check for features
        with open(geojson_path, "r") as file:
            geojson_data = json.load(file)

        # Check if there are features in the GeoJSON
        if not geojson_data.get("features"):
            QtWidgets.QMessageBox.information(
                self,
                "No Earthquakes Found",
                "No earthquakes were found with the current settings.",
            )
            return

        # Safely check and remove the layer
        try:
            if self.loaded_layer:
                QgsProject.instance().removeMapLayer(self.loaded_layer.id())
        except RuntimeError:
            # Layer was already deleted, so just clear the reference
            pass

        # Get the date range from the widgets
        start_date = self.dateFromTimeEdit.date().toString("yyyy-MM-dd")
        end_date = self.dateUntilTimeEdit.date().toString("yyyy-MM-dd")

        # Construct the new layer name
        layer_name_with_date = f"{layer_name} {start_date} to {end_date}"

        # Load the GeoJSON file as a vector layer
        layer = QgsVectorLayer(geojson_path, layer_name_with_date, "ogr")
        if not layer.isValid():
            self.show_error("Failed to load GeoJSON layer.")
            return

        # Apply simple symbology
        self.apply_simple_earthquake_symbology(layer)

        # Add the layer to the QGIS project
        QgsProject.instance().addMapLayer(layer)

        # Save the layer reference
        self.loaded_layer = layer

    def reset_values(self):
        """Reset all values in the widgets and remove the created layer."""
        # Remove "Custom range" from the combo box if it exists
        custom_range_index = self.timeComboBox.findText("Custom range")
        if custom_range_index != -1:
            self.timeComboBox.removeItem(custom_range_index)

        # Reset the timeComboBox to the default placeholder
        self.timeComboBox.setCurrentIndex(0)

        # Reset the areaComboBox to the default placeholder
        self.areaComboBox.setCurrentIndex(0)

        # Reset date/time edits
        self.update_time_range()  # Reset dateFromTimeEdit and dateUntilTimeEdit

        # Reset spin boxes to their default values
        self.magMinSpinBox.setValue(0)
        self.magMaxSpinBox.setValue(7)
        self.depthMinSpinBox.setValue(0)
        self.depthMaxSpinBox.setValue(25)

        # Safely check and remove the layer
        try:
            if self.loaded_layer:
                QgsProject.instance().removeMapLayer(self.loaded_layer.id())
        except RuntimeError:
            # Layer was already deleted, so just clear the reference
            pass

        # Clear the layer reference
        self.loaded_layer = None

        # Refresh the map canvas
        self.iface.mapCanvas().refresh()

    def apply_simple_earthquake_symbology(self, layer):
        """Apply a simple circle symbology to the earthquake layer."""
        if not layer or not layer.isValid():
            return

        # Create a basic symbol with a circle
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        if symbol is not None:
            marker_layer = QgsSimpleMarkerSymbolLayer()
            marker_layer.setColor(QColor("#d73027"))  # Set a default red color
            marker_layer.setSize(4.0)  # Default size in mm
            symbol.changeSymbolLayer(0, marker_layer)

        # Apply a single symbol renderer
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def show_error(self, message):
        """Show an error message to the user."""
        QtWidgets.QMessageBox.critical(self, "Error", message)

    def update_time_range(self):
        """Update the date/time range based on the timeComboBox selection."""
        self.updating_time_range = True  # Set the flag
        current_time = QDateTime.currentDateTime()
        selected_text = self.timeComboBox.currentText()

        # Default: Reset to current day
        start_time = current_time.addDays(-7)  # Default: 7 days
        end_time = current_time

        if selected_text == "Last 1 hour":
            start_time = current_time.addSecs(-3600)  # 1 hour
        elif selected_text == "Last 3 hours":
            start_time = current_time.addSecs(-3 * 3600)  # 3 hours
        elif selected_text == "Last 6 hours":
            start_time = current_time.addSecs(-6 * 3600)  # 6 hours
        elif selected_text == "Last 12 hours":
            start_time = current_time.addSecs(-12 * 3600)  # 12 hours
        elif selected_text == "Last 24 hours":
            start_time = current_time.addSecs(-24 * 3600)  # 24 hours
        elif selected_text == "Last 2 days":
            start_time = current_time.addDays(-2)  # 2 days
        elif selected_text == "Last 7 days":
            start_time = current_time.addDays(-7)  # 7 days
        elif selected_text == "Last 14 days":
            start_time = current_time.addDays(-14)  # 14 days
        elif selected_text == "Last 30 days":
            start_time = current_time.addDays(-30)  # 30 days
        elif selected_text == "Last 60 days":
            start_time = current_time.addDays(-60)  # 60 days
        elif selected_text == "Last 90 days":
            start_time = current_time.addDays(-90)  # 90 days
        elif selected_text == "Last 365 days":
            start_time = current_time.addDays(-365)  # 365 days
        else:
            start_time = current_time.addDays(-7)  # Default: 7 days

        # Round start_time and end_time to the nearest half-hour
        def round_to_nearest_half_hour(qdatetime):
            minute = qdatetime.time().minute()
            second = qdatetime.time().second()

            # Calculate difference to the nearest half-hour
            if minute < 15 or (minute == 15 and second == 0):
                adjustment = -(minute * 60 + second)
            elif minute < 45 or (minute == 45 and second == 0):
                adjustment = (30 - minute) * 60 - second
            else:
                adjustment = (60 - minute) * 60 - second

            return qdatetime.addSecs(adjustment)

        start_time = round_to_nearest_half_hour(start_time)
        end_time = round_to_nearest_half_hour(end_time)

        # Update the date/time widgets
        self.dateFromTimeEdit.setDateTime(start_time)
        self.dateUntilTimeEdit.setDateTime(end_time)

        self.updating_time_range = False  # Unset the flag

    def handle_custom_date_change(self):
        """Set the timeComboBox to 'Custom range' when date/time is manually changed."""
        if self.updating_time_range:
            return  # Skip if the date fields are being updated programmatically

        # Add "Custom range" if it doesn't exist
        custom_range_index = self.timeComboBox.findText("Custom range")
        if custom_range_index == -1:
            self.timeComboBox.addItem("Custom range")
            custom_range_index = self.timeComboBox.count() - 1

        # Set the combo box to "Custom range" unless it's already set
        if self.timeComboBox.currentText() != "Custom range":
            self.timeComboBox.setCurrentIndex(custom_range_index)

    def populate_area_combobox(self):
        """Fetch area information from the API and populate the areaComboBox."""
        url = "https://vi-api.vedur.is/skjalftalisa/v1/areas"
        headers = {"Accept": "application/json"}

        # Clear the combo box and prepare to store polygons
        self.areaComboBox.clear()
        self.areaComboBox.addItem("Choose area")  # Placeholder item

        try:
            # Fetch areas from the API
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                response = response.json()

                features = []

                for i in response:
                    id_area = i["id_area"]
                    area_json = i["area_json"]
                    area_name = area_json["name"]
                    area_polygon = [
                        list(coord_xy)
                        for coord_xy in [
                            (coord_yx[1], coord_yx[0])
                            for coord_yx in area_json["polygon"]
                        ]
                    ]
                    area_polygon.append(area_polygon[0])  # Ensure closure
                    area_polygon.reverse()

                    partial_geojson = {
                        "type": "Feature",
                        "properties": {"name": area_name, "id": id_area},
                        "geometry": {"type": "Polygon", "coordinates": [area_polygon]},
                    }

                    features.append(partial_geojson)

                feature_collection_str = json.dumps(
                    {"type": "FeatureCollection", "features": features}
                )

                feature_collection_geojson = json.loads(feature_collection_str)
                self.feature_collection_gdf = gpd.GeoDataFrame.from_features(
                    feature_collection_geojson["features"], crs="EPSG:4326"
                )

                self.feature_collection_gdf["ends_with_vi"] = (
                    self.feature_collection_gdf["name"].str.endswith("- VÍ")
                )
                self.feature_collection_gdf.sort_values(
                    by=["ends_with_vi", "name"],
                    ascending=[False, True],
                    inplace=True,
                    ignore_index=True,
                )
                self.feature_collection_gdf.drop(columns=["ends_with_vi"], inplace=True)

                if not self.feature_collection_gdf.empty:
                    # Populate the combo box
                    for name in self.feature_collection_gdf["name"]:
                        self.areaComboBox.addItem(name)
                    self.areaComboBox.setCurrentIndex(0)  # Set placeholder as default
                else:
                    self.show_error("No areas available.")
            else:
                self.show_error(
                    f"Failed to fetch areas: {response.status_code} - {response.text}"
                )
        except Exception as e:
            self.show_error(f"An error occurred while fetching areas: {str(e)}")

    def display_area_polygon(self, area_name, polygon):
        """Display the selected area's polygon as a separate layer."""
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [polygon]},
                    "properties": {"name": area_name},
                }
            ],
        }

        print(geojson_data)

        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(suffix=".geojson", delete=False) as temp_file:
            geojson_path = temp_file.name
            with open(geojson_path, "w") as file:
                json.dump(geojson_data, file, indent=2)

        layer_name = f"Area: {area_name}"
        layer = QgsVectorLayer(geojson_path, layer_name, "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
        else:
            self.show_error("Failed to load area polygon layer.")

    def handle_area_checkbox(self, state):
        """Handle areaCheckBox toggle."""
        if state == Qt.Checked:
            selected_area = self.areaComboBox.currentText()
            if selected_area in self.area_polygons:
                self.display_area_polygon(
                    selected_area, self.area_polygons[selected_area]
                )
        else:
            # Remove any existing area polygon layer
            layers = QgsProject.instance().mapLayersByName("Area")
            for layer in layers:
                QgsProject.instance().removeMapLayer(layer)

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()
