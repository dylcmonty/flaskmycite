# FND Data Dev Namespace

This folder is reserved for development and experimental data features that must stay out of example portals.

Allowed in this namespace:

- prototype lenses and recognizers
- ad-hoc parsing heuristics
- temporary rendering modes used for internal validation

Policy:

- Experimental modules stay under `mycite-le_fnd/data/dev/**`.
- Example portals (`mycite-ne-example`, `mycite-le-example`) keep only stable engine modules.
- A future runtime flag such as `enable_dev_data_features` may gate these experiments in FND.
