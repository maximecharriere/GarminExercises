import pandas as pd
import requests
import json
import os
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class GarminExercisesCollector:
    def __init__(self):
        # Set locale for detailed exercise data
        self.locale = "en-US"
        
        # Base URLs
        self.base_url = "https://connect.garmin.com/"
        # File paths
        self.exercises_url = f"{self.base_url}web-data/exercises/Exercises.json"
        self.yoga_url = f"{self.base_url}web-data/exercises/Yoga.json"
        self.pilates_url = f"{self.base_url}web-data/exercises/Pilates.json"
        self.mobility_url = f"{self.base_url}web-data/exercises/Mobility.json"
        self.equipment_url = f"{self.base_url}web-data/exercises/exerciseToEquipments.json"
        self.detailed_data_based_url = f"{self.base_url}web-data/exercises/{self.locale}/"
        self.detailed_page_based_url = f"{self.base_url}modern/exercises/"
        self.translations_url = f"{self.base_url}web-translations/exercise_types/exercise_types.properties"

        
        # Cache for translations
        self.translations = {}
        
        # Initialize dataframes for each category
        self.df_exercises = None
        self.df_yoga = None
        self.df_pilates = None
        self.df_mobility = None
        
        # Set for all unique muscles
        self.all_muscles = set()
        # Set for all unique equipment
        self.all_equipment = set()
    
    def fetch_json(self, url):
        """Fetch JSON data from URL"""
        print(f"Fetching data from {url}")
        response = requests.get(url)
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()
    
    def fetch_translations(self):
        """Fetch and parse translations"""
        print(f"Fetching translations from {self.translations_url}")
        response = requests.get(self.translations_url)
        response.raise_for_status()
        
        for line in response.text.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                self.translations[key.strip()] = value.strip()
    
    def get_exercise_name(self, category, name):
        """Get translated exercise name"""
        key = f"{category}_{name}"
        if key not in self.translations:
            raise Exception(f"Translation not found for {key}")
        return self.translations[key]
    
    def process_exercises_data(self):
        """Process Exercises.json data"""
        data = self.fetch_json(self.exercises_url)
        rows = []
        
        for category, cat_data in data['categories'].items():
            for exercise_name, exercise_data in cat_data['exercises'].items():
                # DEBUG: Limit to 10 rows for testing
                if len(rows) >= 10:
                    break
                row = {
                    'CATEGORY_GARMIN': category,
                    'NAME_GARMIN': exercise_name
                }
                
                # Get translated name
                try:
                    row['Name'] = self.get_exercise_name(category, exercise_name)
                except Exception as e:
                    print(f"Warning: {str(e)}")
                    row['Name'] = f"{category} {exercise_name}"
                
                # Check if detailed info exists
                detailed_data_url = f"{self.detailed_data_based_url}{category}/{exercise_name}.json"
                detailed_page_url = f"{self.detailed_page_based_url}{category}/{exercise_name}"
                try:
                    detailed_data = self.fetch_json(detailed_data_url)
                    row['DETAILED_INFO'] = True
                    row['URL'] = detailed_page_url
                    row['DIFFICULTY'] = detailed_data.get('difficulty', '')
                    row['DESCRIPTION'] = detailed_data.get('description', '')
                    
                    # Get image
                    row['IMAGE'] = ""  # Initialize IMAGE field
                    if 'heroImage' in detailed_data and detailed_data['heroImage']:
                        image_url = f"https://connect.garmin.com{detailed_data['heroImage']}"
                        if requests.head(image_url).status_code == 200:
                            row['IMAGE'] = image_url
                    if not row['IMAGE'] and detailed_data.get('videos') and detailed_data['videos'][0].get('thumbnail'):
                        image_url = f"https://connectvideo.garmin.com{detailed_data['videos'][0]['thumbnail']}"
                        if requests.head(image_url).status_code == 200:
                            row['IMAGE'] = image_url
                    
                    # Track muscles
                    if 'primaryMuscles' in detailed_data:
                        self.all_muscles.update(detailed_data['primaryMuscles'])
                        for muscle in detailed_data['primaryMuscles']:
                            row[f"MUSCLE_{muscle}"] = 1
                    
                    if 'secondaryMuscles' in detailed_data:
                        self.all_muscles.update(detailed_data['secondaryMuscles'])
                        for muscle in detailed_data['secondaryMuscles']:
                            if f"MUSCLE_{muscle}" not in row:  # Avoid overwriting primary
                                row[f"MUSCLE_{muscle}"] = 2
                
                except Exception as e:
                    print(f"Could not fetch detailed data for {category}/{exercise_name}: {str(e)}")
                    row['DETAILED_INFO'] = False
                    row['URL'] = ""
                    row['DIFFICULTY'] = ""
                    row['DESCRIPTION'] = ""
                    row['IMAGE'] = ""
                    
                    # Use primary muscles from the main JSON
                    if 'primaryMuscles' in exercise_data:
                        self.all_muscles.update(exercise_data['primaryMuscles'])
                        for muscle in exercise_data['primaryMuscles']:
                            row[f"MUSCLE_{muscle}"] = 1
                    
                    # Secondary muscles from the main JSON
                    if 'secondaryMuscles' in exercise_data:
                        self.all_muscles.update(exercise_data['secondaryMuscles'])
                        for muscle in exercise_data['secondaryMuscles']:
                            if f"MUSCLE_{muscle}" not in row:  # Avoid overwriting primary
                                row[f"MUSCLE_{muscle}"] = 2
                
                rows.append(row)

        
        # Create DataFrame

        df = pd.DataFrame(rows)
        
        # Fill missing muscle values with 0
        for muscle in self.all_muscles:
            if f"MUSCLE_{muscle}" not in df.columns:
                df[f"MUSCLE_{muscle}"] = 0
            else:
                df[f"MUSCLE_{muscle}"] = df[f"MUSCLE_{muscle}"].fillna(0)
        
        self.df_exercises = df
        
        # Process equipment data
        self.process_equipment_data()
    
    def process_equipment_data(self):
        """Process equipment data and add it to the exercises DataFrame"""
        equipment_data = self.fetch_json(self.equipment_url)
        equipment_mapping = {}
        
        # Create a set of unique equipment types
        for category_data in equipment_data:
            for exercise in category_data['exercisesInCategory']:
                self.all_equipment.update(exercise.get('equipmentKeys', []))
                
                # Create mapping from exercise to equipment
                key = f"{category_data['exerciseCategoryKey']}_{exercise['exerciseKey']}"
                equipment_mapping[key] = exercise.get('equipmentKeys', [])
        
        # Add equipment columns to DataFrame
        for equipment in sorted(self.all_equipment):
            self.df_exercises[f"EQUIPMENT_{equipment}"] = 0
            
        # Fill equipment data
        for idx, row in self.df_exercises.iterrows():
            key = f"{row['CATEGORY_GARMIN']}_{row['NAME_GARMIN']}"
            if key in equipment_mapping:
                for equipment in equipment_mapping[key]:
                    self.df_exercises.at[idx, f"EQUIPMENT_{equipment}"] = 1

    def process_yoga_data(self):
        """Process Yoga.json data"""
        yoga_data = self.fetch_json(self.yoga_url)
        pilates_data = self.fetch_json(self.pilates_url)
        rows = []
        
        # Convert pilates data to a lookup dictionary for muscle information
        pilates_lookup = {}
        for category, cat_data in pilates_data['categories'].items():
            for exercise_name, exercise_data in cat_data['exercises'].items():
                pilates_lookup[f"{category}_{exercise_name}"] = exercise_data
        
        for category, cat_data in yoga_data['categories'].items():
            for exercise_name, exercise_data in cat_data['exercises'].items():
                # DEBUG: Limit to 10 rows for testing
                if len(rows) >= 10:
                    break
                row = {
                    'CATEGORY_GARMIN': category,
                    'NAME_GARMIN': exercise_name
                }
                
                # Get translated name
                try:
                    row['Name'] = self.get_exercise_name(category, exercise_name)
                except Exception as e:
                    print(f"Warning: {str(e)}")
                    row['Name'] = f"{category} {exercise_name}"
                
                # For Yoga, look up muscle information in Pilates data as instructed
                pilates_key = f"{category}_{exercise_name}"
                if pilates_key in pilates_lookup:
                    pilates_exercise = pilates_lookup[pilates_key]
                    
                    # Primary muscles
                    if 'primaryMuscles' in pilates_exercise:
                        self.all_muscles.update(pilates_exercise['primaryMuscles'])
                        for muscle in pilates_exercise['primaryMuscles']:
                            row[f"MUSCLE_{muscle}"] = 1
                    
                    # Secondary muscles
                    if 'secondaryMuscles' in pilates_exercise:
                        self.all_muscles.update(pilates_exercise['secondaryMuscles'])
                        for muscle in pilates_exercise['secondaryMuscles']:
                            if f"MUSCLE_{muscle}" not in row:  # Avoid overwriting primary
                                row[f"MUSCLE_{muscle}"] = 2
                else:
                    raise Exception(f"No corresponding exercise found in Pilates data for Yoga exercise: {pilates_key}")
                
                # Try to fetch detailed info
                detailed_data_url = f"{self.detailed_data_based_url}{category}/{exercise_name}.json"
                detailed_page_url = f"{self.detailed_page_based_url}{category}/{exercise_name}"
                try:
                    detailed_data = self.fetch_json(detailed_data_url)
                    row['DETAILED_INFO'] = True
                    row['URL'] = detailed_page_url
                    row['DIFFICULTY'] = detailed_data.get('difficulty', '')
                    row['DESCRIPTION'] = detailed_data.get('description', '')
                    
                    # Get image
                    row['IMAGE'] = ""  # Initialize IMAGE field
                    if 'heroImage' in detailed_data and detailed_data['heroImage']:
                        image_url = f"https://connect.garmin.com{detailed_data['heroImage']}"
                        if requests.head(image_url).status_code == 200:
                            row['IMAGE'] = image_url
                    if not row['IMAGE'] and detailed_data.get('videos') and detailed_data['videos'][0].get('thumbnail'):
                        image_url = f"https://connectvideo.garmin.com{detailed_data['videos'][0]['thumbnail']}"
                        if requests.head(image_url).status_code == 200:
                            row['IMAGE'] = image_url
                            
                except Exception as e:
                    print(f"Could not fetch detailed data for {category}/{exercise_name}: {str(e)}")
                    row['DETAILED_INFO'] = False
                    row['URL'] = ""
                    row['DIFFICULTY'] = ""
                    row['DESCRIPTION'] = ""
                    row['IMAGE'] = ""
                
                rows.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(rows)
        
        # Fill missing muscle values with 0
        for muscle in self.all_muscles:
            if f"MUSCLE_{muscle}" not in df.columns:
                df[f"MUSCLE_{muscle}"] = 0
            else:
                df[f"MUSCLE_{muscle}"] = df[f"MUSCLE_{muscle}"].fillna(0)
        
        self.df_yoga = df

    def process_pilates_data(self):
        """Process Pilates.json data"""
        data = self.fetch_json(self.pilates_url)
        rows = []
        
        for category, cat_data in data['categories'].items():
            for exercise_name, exercise_data in cat_data['exercises'].items():
                # DEBUG: Limit to 10 rows for testing
                if len(rows) >= 10:
                    break
                row = {
                    'CATEGORY_GARMIN': category,
                    'NAME_GARMIN': exercise_name
                }
                
                # Get translated name
                try:
                    row['Name'] = self.get_exercise_name(category, exercise_name)
                except Exception as e:
                    print(f"Warning: {str(e)}")
                    row['Name'] = f"{category} {exercise_name}"
                
                # Try to fetch detailed info
                detailed_data_url = f"{self.detailed_data_based_url}{category}/{exercise_name}.json"
                detailed_page_url = f"{self.detailed_page_based_url}{category}/{exercise_name}"
                try:
                    detailed_data = self.fetch_json(detailed_data_url)
                    row['DETAILED_INFO'] = True
                    row['URL'] = detailed_page_url
                    row['DIFFICULTY'] = detailed_data.get('difficulty', '')
                    row['DESCRIPTION'] = detailed_data.get('description', '')
                    
                    # Get image
                    row['IMAGE'] = ""  # Initialize IMAGE field
                    if 'heroImage' in detailed_data and detailed_data['heroImage']:
                        image_url = f"https://connect.garmin.com{detailed_data['heroImage']}"
                        if requests.head(image_url).status_code == 200:
                            row['IMAGE'] = image_url
                    if not row['IMAGE'] and detailed_data.get('videos') and detailed_data['videos'][0].get('thumbnail'):
                        image_url = f"https://connectvideo.garmin.com{detailed_data['videos'][0]['thumbnail']}"
                        if requests.head(image_url).status_code == 200:
                            row['IMAGE'] = image_url
                            
                except Exception as e:
                    print(f"Could not fetch detailed data for {category}/{exercise_name}: {str(e)}")
                    row['DETAILED_INFO'] = False
                    row['URL'] = ""
                    row['DIFFICULTY'] = ""
                    row['DESCRIPTION'] = ""
                    row['IMAGE'] = ""
                
                # Primary muscles from pilates.json
                if 'primaryMuscles' in exercise_data:
                    self.all_muscles.update(exercise_data['primaryMuscles'])
                    for muscle in exercise_data['primaryMuscles']:
                        row[f"MUSCLE_{muscle}"] = 1
                
                # Secondary muscles from pilates.json
                if 'secondaryMuscles' in exercise_data:
                    self.all_muscles.update(exercise_data['secondaryMuscles'])
                    for muscle in exercise_data['secondaryMuscles']:
                        if f"MUSCLE_{muscle}" not in row:  # Avoid overwriting primary
                            row[f"MUSCLE_{muscle}"] = 2
                
                rows.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(rows)
        
        # Fill missing muscle values with 0
        for muscle in self.all_muscles:
            if f"MUSCLE_{muscle}" not in df.columns:
                df[f"MUSCLE_{muscle}"] = 0
            else:
                df[f"MUSCLE_{muscle}"] = df[f"MUSCLE_{muscle}"].fillna(0)
        
        self.df_pilates = df

    def process_mobility_data(self):
        """Process Mobility.json data"""
        data = self.fetch_json(self.mobility_url)
        rows = []
        
        for category, cat_data in data['categories'].items():
            for exercise_name, exercise_data in cat_data['exercises'].items():
                # DEBUG: Limit to 10 rows for testing
                if len(rows) >= 10:
                    break
                row = {
                    'CATEGORY_GARMIN': category,
                    'NAME_GARMIN': exercise_name
                }
                
                # Get translated name
                try:
                    row['Name'] = self.get_exercise_name(category, exercise_name)
                except Exception as e:
                    print(f"Warning: {str(e)}")
                    row['Name'] = f"{category} {exercise_name}"
                
                # Try to fetch detailed info
                detailed_data_url = f"{self.detailed_data_based_url}{category}/{exercise_name}.json"
                detailed_page_url = f"{self.detailed_page_based_url}{category}/{exercise_name}"
                try:
                    detailed_data = self.fetch_json(detailed_data_url)
                    row['DETAILED_INFO'] = True
                    row['URL'] = detailed_page_url
                    row['DIFFICULTY'] = detailed_data.get('difficulty', '')
                    row['DESCRIPTION'] = detailed_data.get('description', '')
                    
                    # Get image
                    row['IMAGE'] = ""  # Initialize IMAGE field
                    if 'heroImage' in detailed_data and detailed_data['heroImage']:
                        image_url = f"https://connect.garmin.com{detailed_data['heroImage']}"
                        if requests.head(image_url).status_code == 200:
                            row['IMAGE'] = image_url
                    if not row['IMAGE'] and detailed_data.get('videos') and detailed_data['videos'][0].get('thumbnail'):
                        image_url = f"https://connectvideo.garmin.com{detailed_data['videos'][0]['thumbnail']}"
                        if requests.head(image_url).status_code == 200:
                            row['IMAGE'] = image_url
                            
                except Exception as e:
                    print(f"Could not fetch detailed data for {category}/{exercise_name}: {str(e)}")
                    row['DETAILED_INFO'] = False
                    row['URL'] = ""
                    row['DIFFICULTY'] = ""
                    row['DESCRIPTION'] = ""
                    row['IMAGE'] = ""
                
                # Primary muscles from mobility.json
                if 'primaryMuscles' in exercise_data:
                    self.all_muscles.update(exercise_data['primaryMuscles'])
                    for muscle in exercise_data['primaryMuscles']:
                        row[f"MUSCLE_{muscle}"] = 1
                
                # Secondary muscles from mobility.json
                if 'secondaryMuscles' in exercise_data:
                    self.all_muscles.update(exercise_data['secondaryMuscles'])
                    for muscle in exercise_data['secondaryMuscles']:
                        if f"MUSCLE_{muscle}" not in row:  # Avoid overwriting primary
                            row[f"MUSCLE_{muscle}"] = 2
                
                rows.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(rows)
        
        # Fill missing muscle values with 0
        for muscle in self.all_muscles:
            if f"MUSCLE_{muscle}" not in df.columns:
                df[f"MUSCLE_{muscle}"] = 0
            else:
                df[f"MUSCLE_{muscle}"] = df[f"MUSCLE_{muscle}"].fillna(0)
        
        self.df_mobility = df

    def update_sheet(self, sheets_service, spreadsheet_id, sheet_name, dataframe):
        """Update a specific sheet with dataframe data"""
        if dataframe is None or dataframe.empty:
            print(f"No data for sheet {sheet_name}")
            return
        
        # Organize columns in the correct order
        columns = []
        
        # Define column categories
        name_columns = ['Name', 'CATEGORY_GARMIN', 'NAME_GARMIN']
        detail_columns = ['DETAILED_INFO', 'IMAGE', 'URL', 'DIFFICULTY', 'DESCRIPTION']
        
        # Start with the basic columns
        columns.extend([col for col in name_columns if col in dataframe.columns])
        columns.extend([col for col in detail_columns if col in dataframe.columns])
        
        # Add muscle columns
        muscle_columns = sorted([col for col in dataframe.columns if col.startswith('MUSCLE_')])
        columns.extend(muscle_columns)
        
        # Add equipment columns (only for Exercises)
        if sheet_name == 'Exercises':
            equipment_columns = sorted([col for col in dataframe.columns if col.startswith('EQUIPMENT_')])
            columns.extend(equipment_columns)
        
        # Reorder DataFrame
        df_ordered = dataframe[columns]
        
        # Convert image URLs to IMAGE() formulas
        if 'IMAGE' in df_ordered.columns:
            for i, row in df_ordered.iterrows():
                if row['IMAGE'] and isinstance(row['IMAGE'], str) and row['IMAGE'].startswith('http'):
                    # Convert URL to IMAGE formula with fit mode (4) and dimensions of 100x100
                    df_ordered.at[i, 'IMAGE'] = f'=IMAGE("{row["IMAGE"]}", 1)'
        
        # Create two header rows - first for category, second for column name
        header1 = []  # Column Categories
        header2 = []  # Column Names
        
        for col in columns:
            if col in name_columns:
                header1.append('NAME')
                header2.append(col)
            elif col in detail_columns:
                header1.append('DETAILED_INFO')
                if col == 'DETAILED_INFO':
                    header2.append('FOUND')  # Rename DETAILED_INFO to FOUND as requested
                else:
                    header2.append(col)
            elif col.startswith('MUSCLE_'):
                header1.append('MUSCLE_GROUPS')
                # Extract the muscle name without the MUSCLE_ prefix
                header2.append(col[7:])
            elif col.startswith('EQUIPMENT_'):
                header1.append('EQUIPMENT')
                # Extract the equipment name without the EQUIPMENT_ prefix
                header2.append(col[10:])
            else:
                header1.append('')  # Unknown category
                header2.append(col)
        
        # Clear existing data
        sheets_service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:ZZ"
        ).execute()
        
        # Convert dataframe to values format with two header rows
        values = [header1, header2]
        values.extend(df_ordered.values.tolist())
        
        # Update the sheet
        body = {
            'values': values
        }
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        print(f"Updated sheet {sheet_name}")

    def export_to_google_sheets(self):
        """Export data to Google Sheets"""
        # Path to service account credentials file
        credentials = service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/spreadsheets', 
                    'https://www.googleapis.com/auth/drive']
        )
        
        # Create services
        sheets_service = build('sheets', 'v4', credentials=credentials)
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Check if spreadsheet already exists
        spreadsheet_id = self.get_spreadsheet_id(drive_service)
        
        if not spreadsheet_id:
            # Create new spreadsheet
            spreadsheet = {
                'properties': {
                    'title': 'Garmin Exercises Database'
                },
                'sheets': [
                    {'properties': {'title': 'Exercises'}},
                    {'properties': {'title': 'Yoga'}},
                    {'properties': {'title': 'Pilates'}},
                    {'properties': {'title': 'Mobility'}}
                ]
            }
            
            spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet).execute()
            spreadsheet_id = spreadsheet['spreadsheetId']
            
            # Make it publicly viewable
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={'type': 'anyone', 'role': 'reader'},
                fields='id'
            ).execute()
            
            # Grant yourself editor access (replace with your Gmail address)
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={'type': 'user', 'role': 'writer', 'emailAddress': 'hysterresis@gmail.com'},
                fields='id',
                sendNotificationEmail=False
            ).execute()
            
            # Save the spreadsheet ID
            with open('spreadsheet_id.txt', 'w') as f:
                f.write(spreadsheet_id)
        else:
            # If spreadsheet already exists, clean it by deleting and recreating sheets
            self.clean_spreadsheet(sheets_service, spreadsheet_id)
        
        # Update each sheet
        self.update_sheet(sheets_service, spreadsheet_id, 'Exercises', self.df_exercises)
        self.update_sheet(sheets_service, spreadsheet_id, 'Yoga', self.df_yoga)
        self.update_sheet(sheets_service, spreadsheet_id, 'Pilates', self.df_pilates)
        self.update_sheet(sheets_service, spreadsheet_id, 'Mobility', self.df_mobility)
        
        # Get sheet metadata for formatting
        spreadsheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet_metadata['sheets']
        
        requests = []
        
      
        # Define colors for each category
        category_colors = {
            'NAME': {'red': 0.8, 'green': 0.9, 'blue': 0.97},  # Light blue
            'DETAILED_INFO': {'red': 0.96, 'green': 0.8, 'blue': 0.8},  # Light red
            'MUSCLE_GROUPS': {'red': 0.85, 'green': 0.92, 'blue': 0.83},  # Light green
            'EQUIPMENT': {'red': 1.0, 'green': 0.95, 'blue': 0.8}  # Light yellow
        }
        
        # Fixed column widths (in pixels)
        column_widths = {
            0: 400,  # NAME
            1: 150,  # CATEGORY_GARMIN
            2: 150,  # NAME_GARMIN
            3: 60,   # FOUND
            4: 150,  # IMAGE
            5: 60,   # URL
            6: 90,   # DIFFICULTY
            7: 150,  # DESCRIPTION
        }
        
        # Add requests for formatting
        for sheet in sheets:
            sheet_id = sheet['properties']['sheetId']
            sheet_title = sheet['properties']['title']
            
            # Get row count for full column formatting
            row_count = 1000  # Default to a large number
            if 'gridProperties' in sheet['properties']:
                if 'rowCount' in sheet['properties']['gridProperties']:
                    row_count = sheet['properties']['gridProperties']['rowCount']
                    
            # Freeze first 2 rows (headers)
            requests.append({
                'updateSheetProperties': {
                    'properties': {
                        'sheetId': sheet_id,
                        'gridProperties': {
                            'frozenRowCount': 2,
                            'frozenColumnCount': 0
                        }
                    },
                    'fields': 'gridProperties.frozenRowCount,gridProperties.frozenColumnCount'
                }
            })
            
            # Set headers to bold
            requests.append({
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 0,
                        'endRowIndex': 2,
                        'startColumnIndex': 0,
                        'endColumnIndex': 100
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'textFormat': {'bold': True}
                        }
                    },
                    'fields': 'userEnteredFormat.textFormat.bold'
                }
            })
            
            # Center the first header row
            requests.append({
                'repeatCell': {
                    'range': {
                        'sheetId': sheet_id,
                        'startRowIndex': 0,
                        'endRowIndex': 1,
                        'startColumnIndex': 0,
                        'endColumnIndex': 100
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'horizontalAlignment': 'CENTER'
                        }
                    },
                    'fields': 'userEnteredFormat.horizontalAlignment'
                }
            })
            
            # Set fixed column widths
            for col_index, width in column_widths.items():
                requests.append({
                    'updateDimensionProperties': {
                        'range': {
                            'sheetId': sheet_id,
                            'dimension': 'COLUMNS',
                            'startIndex': col_index,
                            'endIndex': col_index + 1
                        },
                        'properties': {
                            'pixelSize': width
                        },
                        'fields': 'pixelSize'
                    }
                })
            
            # For each sheet, get the header row and find spans of identical values
            header_range = f"{sheet_title}!A1:ZZ1"
            header_response = sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=header_range
            ).execute()
            
            if 'values' in header_response:
                header1_values = header_response['values'][0]
                
                # Find spans of identical values and collect column indices by category
                start_idx = 0
                current_value = header1_values[0]
                
                for i in range(1, len(header1_values)):
                    if header1_values[i] != current_value:
                        # If span length > 1, create merge request
                        if i - start_idx > 1:
                            requests.append({
                                'mergeCells': {
                                    'range': {
                                        'sheetId': sheet_id,
                                        'startRowIndex': 0,
                                        'endRowIndex': 1,
                                        'startColumnIndex': start_idx,
                                        'endColumnIndex': i
                                    },
                                    'mergeType': 'MERGE_ALL'
                                }
                            })
                        
                        # Apply color to columns based on category
                        if current_value in category_colors:
                            requests.append({
                                'repeatCell': {
                                    'range': {
                                        'sheetId': sheet_id,
                                        'startRowIndex': 0,
                                        'endRowIndex': row_count,
                                        'startColumnIndex': start_idx,
                                        'endColumnIndex': i
                                    },
                                    'cell': {
                                        'userEnteredFormat': {
                                            'backgroundColor': category_colors[current_value]
                                        }
                                    },
                                    'fields': 'userEnteredFormat.backgroundColor'
                                }
                            })
                            
                        # Update for next span
                        start_idx = i
                        current_value = header1_values[i]
                
                # Check the last span
                if len(header1_values) - start_idx > 1:
                    requests.append({
                        'mergeCells': {
                            'range': {
                                'sheetId': sheet_id,
                                'startRowIndex': 0,
                                'endRowIndex': 1,
                                'startColumnIndex': start_idx,
                                'endColumnIndex': len(header1_values)
                            },
                            'mergeType': 'MERGE_ALL'
                        }
                    })
                    
                # Apply color to the last category
                if current_value in category_colors:
                    requests.append({
                        'repeatCell': {
                            'range': {
                                'sheetId': sheet_id,
                                'startRowIndex': 0,
                                'endRowIndex': row_count,
                                'startColumnIndex': start_idx,
                                'endColumnIndex': len(header1_values)
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': category_colors[current_value]
                                }
                            },
                            'fields': 'userEnteredFormat.backgroundColor'
                        }
                    })
            
            # Set row heights to 100px for data rows (skip header rows)
            requests.append({
                'updateDimensionProperties': {
                    'range': {
                        'sheetId': sheet_id,
                        'dimension': 'ROWS',
                        'startIndex': 2,  # Start from row 3 (after the two header rows)
                        'endIndex': row_count
                    },
                    'properties': {
                        'pixelSize': 103
                    },
                    'fields': 'pixelSize'
                }
            })
            
            # Auto-resize remaining columns that don't have fixed widths
            remaining_columns_request = {
                'autoResizeDimensions': {
                    'dimensions': {
                        'sheetId': sheet_id,
                        'dimension': 'COLUMNS',
                        'startIndex': max(column_widths.keys()) + 1,
                        'endIndex': 100  # Use a large number for all remaining columns
                    }
                }
            }
            requests.append(remaining_columns_request)
        
        # Execute all formatting requests
        if requests:
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, 
                body={'requests': requests}
            ).execute()
            
        # Process filter views for each sheet
        spreadsheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet_metadata['sheets']
        
        # Now create new filter views
        filter_requests = []
        for sheet in sheets:
            sheet_id = sheet['properties']['sheetId']
            sheet_title = sheet['properties']['title']
            
            # Calculate the data range
            header_range = f"{sheet_title}!A1:ZZ"
            range_data = sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=header_range
            ).execute()
            
            if 'values' in range_data:
                num_rows = len(range_data['values'])
                num_cols = max(len(row) for row in range_data['values']) if range_data['values'] else 0
                
                # Create filter view request
                filter_requests.append({
                    'addFilterView': {
                        'filter': {
                            'title': f"{sheet_title} Filter",
                            'range': {
                                'sheetId': sheet_id,
                                'startRowIndex': 1,  # Start from row 2 (index 1)
                                'endRowIndex': num_rows,
                                'startColumnIndex': 0,
                                'endColumnIndex': num_cols
                            }
                        }
                    }
                })

        # Apply new filter views
        if filter_requests:
            try:
                sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={'requests': filter_requests}
                ).execute()
            except HttpError as e:
                print(f"Note when creating filter views: {str(e)}")
        
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    def get_spreadsheet_id(self, drive_service):
        """Get ID of existing spreadsheet or None if not found"""
        # Try to read from file first

        if os.path.exists('spreadsheet_id.txt'):
            with open('spreadsheet_id.txt', 'r') as f:
                
                spreadsheet_id = f.read().strip()
                if spreadsheet_id:
                    return spreadsheet_id
        
        # Otherwise search on Drive
        results = drive_service.files().list(
            q="name='Garmin Exercises Database' and mimeType='application/vnd.google-apps.spreadsheet'",
            spaces='drive',
            fields='files(id)'
        ).execute()
        
        files = results.get('files', [])
        return files[0]['id'] if files else None

    def delete_spreadsheet(self, drive_service):
        """Delete the Google Spreadsheet and remove local ID file"""
        spreadsheet_id = self.get_spreadsheet_id(drive_service)
        
        if spreadsheet_id:
            try:
                # Delete the file from Google Drive
                drive_service.files().delete(fileId=spreadsheet_id).execute()
                print(f"Spreadsheet with ID {spreadsheet_id} has been deleted.")
                
                # Delete the local ID file if it exists
                if os.path.exists('spreadsheet_id.txt'):
                    os.remove('spreadsheet_id.txt')
                    print("Local spreadsheet ID file has been deleted.")
                    
                return True
            except HttpError as e:
                print(f"Error deleting spreadsheet: {str(e)}")
                return False
        else:
            print("No spreadsheet found to delete.")
            return False

    def clean_spreadsheet(self, sheets_service, spreadsheet_id):
        """Clean spreadsheet by deleting all sheets and creating new ones"""
        # Get current sheets
        spreadsheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet_metadata['sheets']
        
        requests = []
        
        # 1. Create a temporary sheet (we need at least one sheet at all times)
        requests.append({
            'addSheet': {
                'properties': {
                    'title': 'TempSheet'
                }
            }
        })
        
        # 2. Delete all existing sheets
        for sheet in sheets:
            sheet_id = sheet['properties']['sheetId']
            sheet_title = sheet['properties']['title']
            
            requests.append({
                'deleteSheet': {
                    'sheetId': sheet_id
                }
            })
        
        # 3. Create new sheets with desired titles
        sheet_titles = ['Exercises', 'Yoga', 'Pilates', 'Mobility']
        for title in sheet_titles:
            requests.append({
                'addSheet': {
                    'properties': {
                        'title': title
                    }
                }
            })
        
        # 4. Delete the temporary sheet (no longer needed)
        # We'll do this in a second batch update after the first one succeeds
        
        # Execute the first batch of requests
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()
        
        # Now find and delete the temporary sheet
        spreadsheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in spreadsheet_metadata['sheets']:
            if sheet['properties']['title'] == 'TempSheet':
                sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        'requests': [{
                            'deleteSheet': {
                                'sheetId': sheet['properties']['sheetId']
                            }
                        }]
                    }
                ).execute()
                break
        
        print("Spreadsheet cleaned by recreating all sheets")
    
    def compare_data(self, current_data, new_data):
        """Compare current sheet data with new data"""
        if len(current_data) != len(new_data):
            return False
        
        for i in range(min(len(current_data), len(new_data))):
            if len(current_data[i]) != len(new_data[i]):
                return False
            
            for j in range(min(len(current_data[i]), len(new_data[i]))):
                if str(current_data[i][j]) != str(new_data[i][j]):
                    return False
        
        return True

    def run(self):
        """Run the entire process"""
        print("Fetching translations...")
        self.fetch_translations()
        
        print("Processing Exercises data...")
        self.process_exercises_data()
        self.df_exercises.to_pickle("df_exercises_backup.pkl")
        # self.df_exercises = pd.read_pickle("df_exercises_backup.pkl")
        
        print("Processing Pilates data...")
        self.process_pilates_data()
        self.df_pilates.to_pickle("df_pilates_backup.pkl")
        # self.df_pilates = pd.read_pickle("df_pilates_backup.pkl")
        
        print("Processing Yoga data...")
        self.process_yoga_data()
        self.df_yoga.to_pickle("df_yoga_backup.pkl")
        # self.df_yoga = pd.read_pickle("df_yoga_backup.pkl")
        
        print("Processing Mobility data...")
        self.process_mobility_data()
        self.df_mobility.to_pickle("df_mobility_backup.pkl")
        # self.df_mobility = pd.read_pickle("df_mobility_backup.pkl")
        
        print("Exporting to Google Sheets...")
        sheet_url = self.export_to_google_sheets()
        
        print(f"Sheet URL: {sheet_url}")

if __name__ == "__main__":
    collector = GarminExercisesCollector()
    collector.run()
