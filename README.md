# Laakkwartier in 3D

An interactive 3D model of Laakkwartier, a district in The Hague. The model is one self-contained `index.html` file.

Live page: https://0-sv.github.io/laakkwartier-3d/

## What it shows

- Each building at its measured height, coloured by district, construction year, or height.
- Streets, water, rail, parks, and trees.
- Traffic volume per street (red, yellow, green) with moving cars.
- Shadows for each hour of 21 June.

## Data sources

| Layer | Source | Licence |
|---|---|---|
| Buildings and heights | [3DBAG](https://3dbag.nl) LoD 1.3 | CC BY 4.0 |
| District boundary, residents | CBS Wijken en Buurten 2023, through PDOK | CC BY 4.0 |
| Streets, water, rail, green, trees | © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors | ODbL |
| Traffic volume | Gemeente Den Haag traffic model 2017, [public ArcGIS layer](https://services1.arcgis.com/sbwSZYQOs4GMs7tr/arcgis/rest/services/MotorvoertuigverkeerIntensiteitTotaal/FeatureServer) | not stated |
| Renderer | [three.js](https://threejs.org) r160, inlined | MIT |

The traffic volumes are modelled values, not live counts. The cars are an illustration of those volumes.

## Rebuild

The build needs Python 3 and no packages.

```bash
cd build
python3 fetch.py   # downloads the source data into build/data
python3 build.py   # writes ../index.html
```
