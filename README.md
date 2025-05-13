# GarminExercisesCollector

> Link to Google Speadsheet : [Garmin Exercises Database](https://docs.google.com/spreadsheets/d/1OaqIaBhPk4xBnkqVPYvFpj2HZNk_ISX0zHgWfA0WXkQ/edit)

A Python project that collects and organizes exercise data from Garmin Connect into a Google Sheets database. This project automatically extracts exercise information, muscle groups, equipment requirements, and other detailed information from Garmin's exercise library.

## Project Overview

This project aggregates exercise data from Garmin Connect for various workout types and presents it in an organized spreadsheet format, making it easy to search and filter exercises based on different criteria such as:
- Exercise name and type
- Primary and secondary muscle groups
- Equipment requirements
- Difficulty level
- Exercise descriptions
- Image
- URL to exercice page

## Data Sources

Garmin Connect provides 9 different types of workouts, but only 4 have associated exercise data. For multiple workout types, the same `Exercises.json` data source is used :

| Workout Type | Exercise Data Source |
|-------------|---------------------|
| Strength    | [Exercises.json](https://connect.garmin.com/web-data/exercises/Exercises.json) |
| Cardio      | [Exercises.json](https://connect.garmin.com/web-data/exercises/Exercises.json) |
| HIIT        | [Exercises.json](https://connect.garmin.com/web-data/exercises/Exercises.json) |
| Yoga        | [Yoga.json](https://connect.garmin.com/web-data/exercises/Yoga.json) |
| Pilates     | [Pilates.json](https://connect.garmin.com/web-data/exercises/Pilates.json) |
| Mobility    | [Mobility.json](https://connect.garmin.com/web-data/exercises/Mobility.json) |
| Run         | No exercises |
| Bike        | No exercises |
| Custom      | No exercises |

Additional data sources:
- [exerciseToEquipments.json](https://connect.garmin.com/web-data/exercises/exerciseToEquipments.json) - Mapping of equipment requirements
- [exercise_types.properties](https://connect.garmin.com/web-translations/exercise_types/exercise_types.properties) - Exercise name translations in English
- Individual exercise webpage: `https://connect.garmin.com/modern/exercises/<CATEGORY>/<EXERCISE_NAME>` ([example](https://connect.garmin.com/modern/exercises/PUSH_UP/PUSH_UP))
- Individual exercise JSON data: `https://connect.garmin.com/web-data/exercises/en-US/<CATEGORY>/<EXERCISE_NAME>.json` ([example](https://connect.garmin.com/web-data/exercises/en-US/PUSH_UP/PUSH_UP.json))

## Detailed Exercise Information

Not all exercises in Garmin Connect have the same level of detail. This script search for exercises with detailed information, and tracks them with a "FOUND" column. Only exercices with detailed information can display a video on the watch, and have a dedicated page on Garmin Connect.

- **Basic exercises**: Include only name, muscle group, and equipement information
- **Detailed exercises**: Include additional data such as:
  - Visual aids (images and/or videos)
  - Difficulty ratings
  - Comprehensive descriptions
  - Step-by-step instructions

## Speadsheet Updates

The Google Speadsheet is automatically updated on a monthly basis to ensure the information stays current with Garmin's exercise library.
