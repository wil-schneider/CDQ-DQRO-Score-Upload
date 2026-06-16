import requests
import time
import json
import os
from dotenv import load_dotenv
from datetime import datetime
import zipfile
import pandas as pd
import shutil
import sys
try:
    import pyodbc
except ImportError:
    pyodbc = None
import logging
import csv




##########################
#
# Client Class
#
##########################

class CDGCAPIClient:
    def __init__(self, base_url, base_api_url, username, password, ):
        self.base_url = base_url
        self.base_api_url = base_api_url
        self.username = username
        self.password = password
        self.session_id = None
        self.org_id = None
        self.jwt_token = None
        self.monitor_uri = None
        self.output_uri = None

        self.logger = logging.getLogger(self.__class__.__name__)
    
    def user_login(self):
        user_login_uri = '/identity-service/api/v1/Login'
        user_login_url = self.base_url + user_login_uri

        user_login_payload = json.dumps({
            "username": self.username,
            "password": self.password
        })

        user_login_headers = {
            'Content-Type': 'application/json'
        }

        user_login_response = requests.post(user_login_url, headers=user_login_headers, data=user_login_payload)
        user_login_response_json = user_login_response.json()

        self.logger.info(f"Logging in user {self.username} to {self.base_url}")
        self.session_id = user_login_response_json['sessionId']
        self.org_id = user_login_response_json['currentOrgId']

        return self.session_id, self.org_id
    
    def get_token(self):
        if not self.session_id:
            raise Exception("Session ID is not set. Please log in first.")
        
        get_token_url = self.base_url + "/identity-service/api/v1/jwt/Token?client_id=idmc_api&nonce=1234"
        get_token_payload = {}
        get_token_headers = {
            'cookie': f'USER_SESSION={self.session_id}',
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }

        get_token_response = requests.post(get_token_url, headers=get_token_headers, data=get_token_payload)
        get_token_response_json = get_token_response.json()

        self.logger.info(f"Getting JWT Token")
        
        self.jwt_token = get_token_response_json['jwt_token']
        
        return self.jwt_token

    def fetch_core_identities(self, query='Business Term'):
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")
        
        asset_url = self.base_api_url + f"/data360/search/v1/assets?knowledgeQuery={query}&segments=summary"

        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }

        core_identity_list = []
        from_param = 0
        size_param = 100
        
        while True:
            self.logger.info('Sleeping')
            time.sleep(1)
            self.logger.info(f'Fetching IDs from URL: {asset_url}')
            
            payload = json.dumps({
                "from": from_param,
                "size": size_param
            })

            response = requests.post(asset_url, headers=headers, data=payload)

            if response.status_code != 200:
                self.logger.info(f"Request failed with response {response.text}")
                raise Exception(f"Request failed with status code {response.status_code}")
            
            response_json = response.json()
            hits = response_json.get('hits', [])

            for hit in hits:
                core_identity_list.append(hit.get("core.identity"))
            
            total_hits = int(response_json["summary"]["total_hits"])

            if from_param + size_param >= total_hits:
                self.logger.info(f"Search Result {from_param} to Search Result {total_hits} Retrieved.")
                self.logger.info(f"All Assets Retrieved, Exiting fetch_core_identities for type {query}")
                break

            # Print Progress
            self.logger.info(f"Gathering Asset ID's from Search API using {query} Asset Type.\n" 
                  f"Current Status: Search Result {from_param} to Search Result {from_param + size_param} out of {total_hits}")
            
            from_param += size_param

        return core_identity_list
    
    def fetch_asset_json(self, query='Business Term'):
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        asset_url = self.base_api_url + f"/data360/search/v1/assets?knowledgeQuery={query}&segments=all"
        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }
        core_identity_list = []
        from_param = 0
        size_param = 100

        while True:
            self.logger.info('Sleeping')
            time.sleep(1)
            self.logger.info(f'Fetching IDs from URL: {asset_url}')

            payload = json.dumps({
                "from": from_param,
                "size": size_param
            })
            response = requests.post(asset_url, headers=headers, data=payload)
            if response.status_code != 200:
                self.logger.info(f"Request failed with response {response.text}")
                raise Exception(f"Request failed with status code {response.status_code}")

            response_json = response.json()
            hits = response_json.get('hits', [])
            for hit in hits:
                # Append the entire hit JSON instead of just core.identity
                core_identity_list.append(hit)

            total_hits = int(response_json["summary"]["total_hits"])
            if from_param + size_param >= total_hits:
                self.logger.info(f"Search Result {from_param} to Search Result {total_hits} Retrieved.")
                self.logger.info(f"All Assets Retrieved, Exiting fetch_core_identities for type {query}")
                break

            self.logger.info(
                f"Gathering Asset ID's from Search API using {query} Asset Type.\n"
                f"Current Status: Search Result {from_param} to Search Result {from_param + size_param} out of {total_hits}"
            )

            from_param += size_param

        return core_identity_list

    def fetch_neighborhood_details_and_export_csv(self, asset_id_list, csv_filename='neighborhood_details.csv'):
        """
        For each asset ID in the list, call the asset details endpoint to get neighborhood details,
        parse the required fields, and write them to a CSV file.

        :param asset_id_list: List of asset IDs (strings)
        :param csv_filename: Output CSV file name
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }

        rows = []
        for asset_id in asset_id_list:
            url = f"{self.base_api_url}/data360/search/v1/assets/{asset_id}?scheme=internal&segments=neighborhood"
            self.logger.info(f"Fetching neighborhood details for asset ID: {asset_id}")
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                self.logger.warning(f"Failed to fetch asset {asset_id}: {response.status_code} {response.text}")
                continue

            data = response.json()
            neighborhood = data.get('neighborhood', [])

            # Parse neighborhood details
            for neighbor_group in neighborhood:
                neighbors = neighbor_group.get('neighbors', [])
                for neighbor in neighbors:
                    paths = neighbor.get('paths', [])
                    for path in paths:
                        collection = path.get('collection', [])
                        for assoc in collection:
                            row = {
                                'from': assoc.get('from', ''),
                                'fromType': assoc.get('fromType', ''),
                                'to': assoc.get('to', ''),
                                'toType': assoc.get('toType', ''),
                                'association': assoc.get('association', '')
                            }
                            rows.append(row)

            # To avoid hitting API rate limits
            time.sleep(0.5)

        # Write to CSV
        if rows:
            with open(csv_filename, mode='w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['from', 'fromType', 'to', 'toType', 'association']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
            self.logger.info(f"Neighborhood details exported to {csv_filename}")
        else:
            self.logger.info("No neighborhood details found to export.")
    
    def start_export_job(self, knowledgeQuery='Business Term', segments='all'):
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")
        
        export_timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        export_url = self.base_api_url + f"/data360/search/export/v1/assets?knowledgeQuery={knowledgeQuery}&segments={segments}&fileName=export_{export_timestamp}&fileType=CSV"

        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }
            
        payload = json.dumps({
            "size": 0
            })
        
        export_response = requests.request("POST", 
                                           export_url, headers=headers, data=payload)

        export_response_json = export_response.json()
        self.logger.info(export_response_json)

        # Set monitor and download URI's as retrieved from export response
        self.monitor_uri = export_response_json['trackingURI']
        self.output_uri = export_response_json['outputURI']

        return 
    
    def start_export_all_assets_job(self):
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")
        
        export_timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        export_url = self.base_api_url + f"/data360/search/export/v1/assets?knowledgeQuery=Catalog Source&segments=all&fileName=export_all_{export_timestamp}&fileType=CSV"

        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }
            
        payload = json.dumps({
            "size": 0
            })
        
        export_response = requests.request("POST", 
                                           export_url, headers=headers, data=payload)

        export_response_json = export_response.json()
        self.logger.info(export_response_json)

        # Set monitor and download URI's as retrieved from export response
        self.monitor_uri = export_response_json['trackingURI']
        self.output_uri = export_response_json['outputURI']

        return 
    
    def monitor_export_job(self, max_retries=5):
        url = self.base_api_url + self.monitor_uri

        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }

        retries = 0
        while retries < max_retries:
            try:
                # Make the request
                monitor_response = requests.request("GET", url, headers=headers, data={})
                
                # Check if the request was successful
                if monitor_response.status_code == 200:
                    monitor_response_json = monitor_response.json()
                    job_status = monitor_response_json.get("status")
                    return job_status
                
                # Retry logic for specific status codes
                elif monitor_response.status_code == 429 or monitor_response.status_code == 500:
                    retries += 1
                    backoff_time = 2 ** retries
                    self.logger.info(f"Received {monitor_response.status_code}. Retrying in {backoff_time} seconds...")
                    time.sleep(backoff_time)

                # If response is 401 Unauthorized, reauthenticate and update the token
                elif monitor_response.status_code == 401:
                    self.logger.info("Unauthorized error encountered. Re-authenticating...")
                    # Reauthenticate
                    self.user_login()  # This updates the session_id and org_id
                    self.jwt_token = self.get_token()  # This updates the jwt_token
                    headers['Authorization'] = f'Bearer {self.jwt_token}'  # Update the token in the headers
                    
                    # Retry the request with the new token
                    monitor_response = requests.get(url, headers=headers)

                else:
                    self.logger.info(f"Unexpected error occurred: {monitor_response.status_code} - {monitor_response.text}")
                    break

            except requests.exceptions.RequestException as e:
                self.logger.info(f"An error occurred while making the request: {str(e)}")
                break

        self.logger.info(f"Failed to monitor export job after {max_retries} retries. Exiting...")
        sys.exit(1)

    def download_export_job(self):
        # Reauthenticate before downloading
        self.user_login()  # This updates the session_id and org_id
        self.jwt_token = self.get_token()  # This updates the jwt_token
        
        self.logger.info("Sleeping 5 seconds for Download")
        time.sleep(5)

        download_url = self.base_api_url + self.output_uri
        download_payload = {}
        download_headers = {
        'X-INFA-ORG-ID': f'{self.org_id}',
        'Authorization': f'Bearer {self.jwt_token}'
        }

        # Download the file
        download_timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.logger.info(f"Attempting to download from {download_url}")
        download_response = requests.request("GET", download_url, headers=download_headers, data=download_payload, stream=True)
        download_filename = f'resource_dl_{download_timestamp}.zip'
        self.logger.info(f'Download Filename {download_filename}')

        self.logger.info(download_response.status_code)

        # Check if the request was successful, if so, write to .zip file
        if download_response.status_code == 200:
            # Open a file in write-binary mode
            with open(download_filename, 'wb') as f:
                # Write the response content to the file in chunks
                for chunk in download_response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)

        return download_filename
    
    def fetch_resource_origin(self, query='Catalog Source ORA_MSS_MSSW_TEST'):
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")
        
        asset_url = self.base_api_url + f"/data360/search/v1/assets?knowledgeQuery={query}&segments=all"

        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }

        from_param = 0
        size_param = 100
        
        while True:
            self.logger.info('Sleeping')
            time.sleep(1)
            self.logger.info(f'Fetching IDs from URL: {asset_url}')
            
            payload = json.dumps({
                "from": from_param,
                "size": size_param
            })

            response = requests.post(asset_url, headers=headers, data=payload)

            if response.status_code != 200:
                self.logger.info(f"Request failed with response {response.text}")
                raise Exception(f"Request failed with status code {response.status_code}")
            
            response_json = response.json()
            
            # Get total_hits safely and convert to int if needed
            total_hits_str = response_json.get('summary', {}).get('total_hits', '0')
            try:
                total_hits = int(total_hits_str)
            except ValueError:
                total_hits = 0
            
            if total_hits == 1:
                hits = response_json.get('hits', [])
                if hits:
                    core_origin = hits[0].get('systemAttributes', {}).get('core.origin')
                    return core_origin
                else:
                    self.logger.info("No Origin found though total_hits was 1.")
                    return None
            else:
                self.logger.info(f"Total hits is {total_hits}, not equal to 1. Returning None.")
                return None

    def delete_asset(self, asset_id, scheme='INTERNAL'):

        asset_url = self.base_api_url + f"/data360/content/v1/assets/{asset_id}?scheme={scheme}"

        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token
        }

        response = requests.delete(asset_url, headers=headers)

        return response
    
    def create_asset(self):

        asset_url = self.base_api_url + f"/data360/content/v1/assets"

        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token
        }

        body = {
            "core.classType": "com.infa.ccgf.models.governance.BusinessTerm",
            "summary": {
                "core.name": "wsNet Profit",
                "core.description": "Net income value of the Income Statement"
                }
        }

        response = requests.post(asset_url, headers=headers, json=body)

        return response

    def get_catalog_source_config(self, catalog_source_name):
        if not all([self.org_id, self.session_id, self.jwt_token]):
            raise Exception("Authentication details missing. Please login and get token first.")

        url = f"{self.base_api_url}/data360/catalog-source-management/v1/catalogsources/{catalog_source_name}"
        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'IDS-SESSION-ID': self.session_id,
            'Authorization': f'Bearer {self.jwt_token}'
        }
        response = requests.get(url, headers=headers)
        self.logger.info(f"Fetching catalog source config for '{catalog_source_name}'")
        response.raise_for_status()  # Raise exception for HTTP errors
        config_json = response.json()

        # Save to JSON file
        filename = f"base_{catalog_source_name}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(config_json, f, indent=2)
        self.logger.info(f"Saved catalog source config to {filename}")

        return config_json
    
    def update_filter_values(self, config_json, new_values_list):
        """
        Update the 'values' list for the configOption with key 'Filter Value' in the given config JSON.

        Args:
            config_json (dict): The JSON object representing the configuration.
            new_values_list (list): The new list of values to set for the 'Filter Value' key.

        Returns:
            dict: The updated JSON object.
        """
        # Use a stack to keep track of objects to visit (iterative approach)
        stack = [config_json]

        while stack:
            current = stack.pop()

            if isinstance(current, dict):
                # Check if this dict has the key 'key' with value 'Filter Value'
                if current.get('key') == 'Filter Value':
                    current['values'] = new_values_list
                    self.logger.info(f"Updated Filter Value to: {new_values_list}")
                    return config_json  # Return early after update

                # Add all values of the dict to the stack to visit next
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)

            elif isinstance(current, list):
                # Add all items in the list to the stack to visit next
                for item in current:
                    if isinstance(item, (dict, list)):
                        stack.append(item)

        # If we finish the loop without finding the key, raise an error
        raise ValueError("No 'Filter Value' key found in the provided JSON.")

    def clean_update_payload(self, config_json):
        """
        Remove fields from the config JSON that are not needed or cause errors in the update API.

        Args:
            config_json (dict): The full catalog source config JSON.

        Returns:
            dict: Cleaned config JSON suitable for update API.
        """
        keys_to_remove = [
            "id",
            "endOfLife",
            "seedVersion",
            "isDeleted",
            "createdBy",
            "lastModifiedBy",
            "createdTime",
            "lastModifiedTime",
            "modelVersion"
        ]

        cleaned = dict(config_json)  # shallow copy

        for key in keys_to_remove:
            cleaned.pop(key, None)

        return cleaned

    def update_catalog_source_config(self, catalog_source_name, updated_config):
        """
        Update a catalog source configuration in Informatica via API.

        Args:
            catalog_source_name (str): The name of the catalog source to update.
            updated_config (dict): The updated configuration JSON object.

        Returns:
            dict: The response JSON from the API.
        """
        if not all([self.org_id, self.session_id, self.jwt_token]):
            raise Exception("Authentication details missing. Please login and get token first.")

        cleaned_config = self.clean_update_payload(updated_config)

        url = f"{self.base_api_url}/data360/catalog-source-management/v1/catalogsources/{catalog_source_name}"
        
        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'IDS-SESSION-ID': self.session_id,
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.jwt_token}'
        }
        
        payload = json.dumps(cleaned_config)
        
        self.logger.info(f"Updating catalog source config for '{catalog_source_name}'")
        response = requests.put(url, headers=headers, data=payload)
        response.raise_for_status()
        
        self.logger.info(f"Successfully updated catalog source '{catalog_source_name}'")
        return response.json()

    def update_filter_configuration(self, config_json, filter_values=None):

        if filter_values is None:
            filter_values = ["wilsandbox2.dbo.students_class_a"]

        type_capabilities = config_json.get("typeCapabilities", [])
        profiling_filter_configs = None
        capability = None

        for cap in type_capabilities:
            if cap.get("capabilityName") == "Data Profiling":
                for config_prop in cap.get("configurationProperties", []):
                    if config_prop.get("optionGroupName") == "Profiling Filter Config":
                        profiling_filter_configs = config_prop
                        capability = cap
                        break
                if profiling_filter_configs:
                    break

        if profiling_filter_configs is None:
            raise ValueError("Profiling Filter Config section not found in the configuration.")

        if len(filter_values) == 1:
            for option in profiling_filter_configs.get("configOptions", []):
                if option.get("key") == "Filter Value":
                    option["values"] = filter_values
                    self.logger.info(f"Updated Filter Value to: {filter_values}")
                    break
        else:
            capability["configurationProperties"].remove(profiling_filter_configs)

            new_filter_entries = []
            for val in filter_values:
                new_filter_entries.append({
                    "optionGroupName": "Profiling Filter Config",
                    "configOptions": [
                        {
                            "key": "Filter Pivot",
                            "values": ["Include Metadata"],
                            "additionalMetadata": None
                        },
                        {
                            "key": "Filter Type",
                            "values": ["Tables"],
                            "additionalMetadata": None
                        },
                        {
                            "key": "Filter Value",
                            "values": [val],
                            "additionalMetadata": None
                        }
                    ]
                })

            capability["configurationProperties"].extend(new_filter_entries)
            self.logger.info(f"Replaced Filter Config with {len(filter_values)} separate entries.")

        return config_json
    
    def get_audit_history(self,
                        asset_types=['com.infa.ccgf.models.governance.BusinessTerm'],
                        timestamp_ge='2025-05-01T00:00:00.000Z',
                        page_size=100):
        """
        Fetch full audit history with pagination, building query string manually.

        :param asset_types: List of asset type strings (default to BusinessTerm)
        :param timestamp_ge: Timestamp string in ISO 8601 format (default to '2025-05-01T00:00:00.000Z')
        :param page_size: Number of records per page (default 100)
        :return: List of all audit events combined from all pages
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        all_events = []
        offset = 0

        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'XSRF_TOKEN': self.session_id,
            'IDS-CSRF-TOKEN': self.session_id,
            'IDS-SESSION-ID': self.session_id
        }

        asset_types_str = ",".join(asset_types)
        audit_url = self.base_api_url + "/data360/audit/v1/assets/events"

        while True:
            query_string = (
                f"offset={offset}"
                f"&limit={page_size}"
                f"&filter=timestamp:GE:({timestamp_ge})"
                f"&filter=assetTypes:IN:({asset_types_str})"
            )

            full_url = audit_url + "?" + query_string

            self.logger.info(f"Fetching audit history from URL: {full_url}")

            response = requests.get(full_url, headers=headers)
            if response.status_code != 200:
                self.logger.error(f"Audit history request failed: {response.text}")
                raise Exception(f"Audit history request failed with status code {response.status_code}")

            response_json = response.json()
            events = response_json.get('events', [])
            summary = response_json.get('summary', {})
            response_size = summary.get('responseSize', 0)
            total_size = summary.get('totalSize', 0)

            all_events.extend(events)

            self.logger.info(f"Fetched {response_size} events, total collected: {len(all_events)} / {total_size}")

            if offset + response_size >= total_size:
                self.logger.info("All audit events retrieved.")
                break

            offset += response_size

        return all_events

    def update_asset_description(self, asset_id, description):
        """
        Update the description of an asset using the PATCH API.

        :param asset_id: str, the UUID of the asset to update
        :param description: str, the new description to set
        :return: response JSON or raises Exception on failure
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        url = f"{self.base_api_url}/data360/content/v1/assets/{asset_id}?scheme=INTERNAL"
        payload = json.dumps([
            {
                "operation": "add",
                "segment": "summary",
                "attributes": {
                    "core.description": description
                }
            }
        ])
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }

        response = requests.patch(url, headers=headers, data=payload)
        if response.status_code not in (200, 204):
            self.logger.error(f"Failed to update asset description: {response.status_code} {response.text}")
            raise Exception(f"Failed to update asset description: {response.status_code} {response.text}")

        self.logger.info(f"Successfully updated description for asset {asset_id}")
        try:
            return response.json()
        except ValueError:
            # No content to decode
            return None
    
    def fetch_core_identity_details(self, query='Business Term'):
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        asset_url = self.base_api_url + f"/data360/search/v1/assets?knowledgeQuery={query}&segments=summary"
        headers = {
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.jwt_token,
            'XSRF_TOKEN': f'{self.session_id}',
            'IDS-CSRF-TOKEN': f'{self.session_id}',
            'IDS-SESSION-ID': f'{self.session_id}'
        }
        core_identity_details_list = []
        from_param = 0
        size_param = 100

        while True:
            self.logger.info('Sleeping')
            time.sleep(1)
            self.logger.info(f'Fetching assets from URL: {asset_url}')
            payload = json.dumps({
                "from": from_param,
                "size": size_param
            })
            response = requests.post(asset_url, headers=headers, data=payload)
            if response.status_code != 200:
                self.logger.info(f"Request failed with response {response.text}")
                raise Exception(f"Request failed with status code {response.status_code}")

            try:
                response_json = response.json()
            except ValueError as e:
                self.logger.error(f"Failed to parse JSON response: {e}")
                break

            hits = response_json.get('hits', [])
            for hit in hits:
                asset_dict = {
                    "core.identity": hit.get("core.identity", ""),
                    "core.externalId": hit.get("core.externalId", ""),
                    "core.name": hit.get("summary", {}).get("core.name", ""),
                    "core.description": hit.get("summary", {}).get("core.description", ""),
                    # Additional fields default to empty strings
                    "translated_name": "",
                    "gis_id": "",
                    "gis_name": "",
                    "gis_description": ""
                }
                core_identity_details_list.append(asset_dict)

            summary = response_json.get("summary")
            if not summary:
                self.logger.warning(f"'summary' key missing in response for query: {query}. Possibly table not found.")
                break

            total_hits = summary.get("total_hits")
            if total_hits is None:
                self.logger.warning(f"'total_hits' missing in summary for query: {query}.")
                break

            try:
                total_hits = int(total_hits)
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid 'total_hits' value: {total_hits} for query: {query}.")
                break

            if from_param + size_param >= total_hits:
                self.logger.info(f"Search Result {from_param} to Search Result {total_hits} Retrieved.")
                self.logger.info(f"All Assets Retrieved, Exiting fetch_core_identity_details for type {query}")
                break

            self.logger.info(
                f"Gathering Asset details from Search API using {query} Asset Type.\n"
                f"Current Status: Search Result {from_param} to Search Result {from_param + size_param} out of {total_hits}"
            )
            from_param += size_param

        return core_identity_details_list

