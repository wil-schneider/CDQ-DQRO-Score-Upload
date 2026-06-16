"""
CDGCAPIClientV2 - Enhanced API Client for Informatica Cloud Data Governance and Catalog

This module extends CDGCAPIClient with high-priority endpoints identified from the API documentation:
- Import assets (bulk operations)
- Advanced search with filtering
- Relationship management
- Single asset detail retrieval
- Data quality score uploads

Author: Claude Code
Version: 2.0
"""

import requests
import json
import logging
from CDGCAPIClient import CDGCAPIClient


class CDGCAPIClientV2(CDGCAPIClient):
    """
    Enhanced CDGC API Client (Version 2)

    Inherits from CDGCAPIClient and adds high-priority endpoints:
    - Import assets from Excel/CSV
    - Advanced search with filterSpec/rankingSpec
    - Relationship management (create/delete)
    - Get single asset details
    - Upload data quality scores
    """

    def __init__(self, base_url, base_api_url, username, password):
        """
        Initialize the V2 client with the same parameters as V1

        Args:
            base_url: Base URL for authentication (e.g., https://dm-us.informaticacloud.com)
            base_api_url: Base API URL (e.g., https://idmc-api.dm-us.informaticacloud.com)
            username: IICS username
            password: IICS password
        """
        super().__init__(base_url, base_api_url, username, password)
        self.logger = logging.getLogger(self.__class__.__name__)

    ##########################
    # Import Assets
    ##########################

    def import_assets(self, file_path, validation_policy='CONTINUE_ON_ERROR_WARNING'):
        """
        Import bulk assets from Excel or CSV file

        Args:
            file_path: Full path to the import file (.xlsx, .xlsm, .xlsb, .xls, or .csv)
            validation_policy: How to handle errors/warnings. Options:
                - 'CONTINUE_ON_ERROR_WARNING' (default): Import valid rows, skip errors/warnings
                - 'STOP_ON_ERROR': Stop if any errors found, skip warnings
                - 'STOP_ON_WARNING': Stop if any warnings found

        Returns:
            dict: Response containing jobId and jobUri for monitoring

        Raises:
            Exception: If JWT token is not available or file doesn't exist
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        import os
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Import file not found: {file_path}")

        import_url = self.base_api_url + '/data360/content/import/v1/assets'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id
        }

        # Prepare config as JSON string
        config_data = {
            "validationPolicy": validation_policy
        }

        # Prepare multipart form data
        files = {
            'file': open(file_path, 'rb'),
            'config': (None, json.dumps(config_data), 'application/json')
        }

        self.logger.info(f"Importing assets from file: {file_path}")
        self.logger.info(f"Validation policy: {validation_policy}")

        try:
            response = requests.post(import_url, headers=headers, files=files)
            response.raise_for_status()

            result = response.json()
            self.logger.info(f"Import job started. Job ID: {result.get('jobId')}")

            return result
        finally:
            files['file'].close()

    def monitor_import_job(self, job_id):
        """
        Monitor the status of an import job

        Args:
            job_id: The job ID returned from import_assets()

        Returns:
            dict: Job status information
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        job_url = self.base_api_url + f'/data360/observable/v1/jobs/{job_id}'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id
        }

        response = requests.get(job_url, headers=headers)
        response.raise_for_status()

        return response.json()

    ##########################
    # Advanced Search
    ##########################

    def search_assets_advanced(self, knowledge_query='*', filter_spec=None, ranking_spec=None,
                               from_offset=0, size=100, segments='all'):
        """
        Advanced asset search with filtering, ranking, and sorting

        Args:
            knowledge_query: Search query string (default: '*' for all)
            filter_spec: List of filter specifications. Examples:
                Simple filter: [{"type": "simple", "attribute": "core.classType",
                                "values": ["com.infa.ccgf.models.governance.BusinessTerm"]}]
                DSL filter: [{"type": "dsl", "expr": "core.classType com.infa.ccgf.models.governance.BusinessTerm
                             and core.createdOn within last 30 day"}]
            ranking_spec: Dictionary with boostSpec and/or scoringSpec for result ordering
            from_offset: Pagination offset (default: 0)
            size: Number of results per page (default: 100, max: 100)
            segments: Level of detail ('all', 'summary', 'systemAttributes', 'customAttributes',
                     'selfAttributes', 'details')

        Returns:
            dict: Search results with assets and metadata
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        search_url = self.base_api_url + f'/data360/search/v1/assets?knowledgeQuery={knowledge_query}&segments={segments}'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json'
        }

        # Build request body
        body = {
            "from": from_offset,
            "size": size
        }

        if filter_spec:
            body["filterSpec"] = filter_spec

        if ranking_spec:
            body["rankingSpec"] = ranking_spec

        self.logger.info(f"Advanced search: query='{knowledge_query}', from={from_offset}, size={size}")

        response = requests.post(search_url, headers=headers, data=json.dumps(body))
        response.raise_for_status()

        return response.json()

    def search_with_pagination(self, knowledge_query='*', after_values=None,
                              sort_attribute='core.identity', sort_order='asc',
                              size=100, segments='all'):
        """
        Search assets with cursor-based pagination (supports >10K results)

        Args:
            knowledge_query: Search query string
            after_values: List of sort values from previous page's last result (for next page)
            sort_attribute: Attribute to sort by (must have unique values like 'core.identity')
            sort_order: 'asc' or 'desc'
            size: Number of results per page (max: 100)
            segments: Level of detail to return

        Returns:
            dict: Search results with sortValues for pagination
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        search_url = self.base_api_url + f'/data360/search/v1/assets?knowledgeQuery={knowledge_query}&segments={segments}'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json'
        }

        body = {
            "size": size,
            "rankingSpec": {
                "scoringSpec": [
                    {
                        "type": "simple",
                        "attribute": sort_attribute,
                        "order": sort_order
                    }
                ]
            }
        }

        if after_values:
            body["after"] = after_values

        response = requests.post(search_url, headers=headers, data=json.dumps(body))
        response.raise_for_status()

        return response.json()

    def get_asset_details(self, asset_id, scheme='internal', segments='all'):
        """
        Get detailed information about a specific asset

        Args:
            asset_id: Internal ID or external ID of the asset
            scheme: 'internal' or 'external' - type of asset_id provided
            segments: Level of detail ('all', 'summary', 'systemAttributes', etc.)

        Returns:
            dict: Asset details
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        asset_url = self.base_api_url + f'/data360/search/v1/assets/{asset_id}?scheme={scheme}&segments={segments}'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id
        }

        self.logger.info(f"Getting asset details: {asset_id} (scheme: {scheme})")

        response = requests.get(asset_url, headers=headers)
        response.raise_for_status()

        return response.json()

    def get_multiple_asset_details(self, asset_ids, scheme='internal', segments='all'):
        """
        Get details for multiple specific assets by their IDs

        Args:
            asset_ids: List of asset IDs (internal or external)
            scheme: 'internal' or 'external' - type of asset IDs provided
            segments: Level of detail to return

        Returns:
            dict: Details for all requested assets
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        details_url = self.base_api_url + f'/data360/search/v1/assets/details?scheme={scheme}&segments={segments}'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json'
        }

        body = {
            "assetIds": asset_ids
        }

        self.logger.info(f"Getting details for {len(asset_ids)} assets")

        response = requests.post(details_url, headers=headers, data=json.dumps(body))
        response.raise_for_status()

        return response.json()

    ##########################
    # Relationship Management
    ##########################

    def create_relationship(self, from_identity, to_identity, association_type,
                           from_scheme='internal', to_scheme='internal', use_external_ids=False):
        """
        Create a relationship between two assets

        Args:
            from_identity: Source asset ID (internal or external based on scheme)
            to_identity: Target asset ID (internal or external based on scheme)
            association_type: Type of relationship (e.g., 'com.infa.ccgf.models.governance.relatedBusinessTerm')
            from_scheme: 'internal' or 'external' for from_identity
            to_scheme: 'internal' or 'external' for to_identity
            use_external_ids: If True, uses fromExternalIdentity/toExternalIdentity fields

        Returns:
            requests.Response: API response
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        update_url = self.base_api_url + f'/data360/content/v1/assets/{from_identity}?scheme={from_scheme}'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json'
        }

        # Build relationship item
        relationship_item = {
            "association": association_type
        }

        if use_external_ids:
            relationship_item["fromExternalIdentity"] = from_identity
            relationship_item["toExternalIdentity"] = to_identity
        else:
            relationship_item["fromIdentity"] = from_identity
            relationship_item["toIdentity"] = to_identity

        body = {
            "operation": "add",
            "segment": "relationship",
            "items": [relationship_item]
        }

        self.logger.info(f"Creating relationship: {from_identity} -> {to_identity} ({association_type})")

        response = requests.patch(update_url, headers=headers, data=json.dumps(body))
        response.raise_for_status()

        return response

    def delete_relationship(self, from_identity, to_identity, association_type,
                           from_scheme='internal', to_scheme='internal', use_external_ids=False):
        """
        Delete a relationship between two assets

        Args:
            from_identity: Source asset ID
            to_identity: Target asset ID
            association_type: Type of relationship to delete
            from_scheme: 'internal' or 'external' for from_identity
            to_scheme: 'internal' or 'external' for to_identity
            use_external_ids: If True, uses fromExternalIdentity/toExternalIdentity fields

        Returns:
            requests.Response: API response
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        update_url = self.base_api_url + f'/data360/content/v1/assets/{from_identity}?scheme={from_scheme}'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json'
        }

        # Build relationship item
        relationship_item = {
            "association": association_type
        }

        if use_external_ids:
            relationship_item["fromExternalIdentity"] = from_identity
            relationship_item["toExternalIdentity"] = to_identity
        else:
            relationship_item["fromIdentity"] = from_identity
            relationship_item["toIdentity"] = to_identity

        body = {
            "operation": "remove",
            "segment": "relationship",
            "items": [relationship_item]
        }

        self.logger.info(f"Deleting relationship: {from_identity} -> {to_identity} ({association_type})")

        response = requests.patch(update_url, headers=headers, data=json.dumps(body))
        response.raise_for_status()

        return response

    ##########################
    # Data Quality Scores
    ##########################

    def import_dq_scores_from_csv(self, file_path):
        """
        Import data quality scores from a CSV file (April 2026 API).

        This replaces upload_dq_scores() which uses the deprecated PATCH endpoint
        (supported until July 2026). Triggers an async job; use monitor_import_job()
        to track completion.

        Args:
            file_path: Path to a CSV file (max 10 MB) with columns:
                - Reference ID: Reference ID of the rule occurrence
                - Score: Numeric 0-100 (no percent sign)
                - Total Rows: Positive integer
                - Failed Rows: Positive integer
                - Scanned Time: YYYY-MM-dd'T'HH:mm:ss.SSS'Z' format
                - Exception File Path: Full path to exception records file

        Returns:
            dict: Response with 'jobId' and 'jobUri' for monitoring via monitor_import_job()

        Raises:
            Exception: If JWT token is not available or file doesn't exist
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        import os
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Import file not found: {file_path}")

        dq_import_url = self.base_api_url + '/data-quality/v1/rule-occurrences/runs'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id
        }

        self.logger.info(f"Importing DQ scores from CSV file: {file_path}")

        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, 'text/csv')}
            response = requests.post(dq_import_url, headers=headers, files=files)

        if response.status_code == 401:
            self.logger.info("Token expired, re-authenticating...")
            self.user_login()
            self.get_token()
            headers['Authorization'] = 'Bearer ' + self.jwt_token
            with open(file_path, 'rb') as f:
                files = {'file': (os.path.basename(file_path), f, 'text/csv')}
                response = requests.post(dq_import_url, headers=headers, files=files)

        if not response.ok:
            raise Exception(f"DQ score upload failed ({response.status_code}): {response.text}")
        response.raise_for_status()

        result = response.json()
        self.logger.info(f"DQ score import job started. Job ID: {result.get('jobId')}")

        return result

    def upload_dq_scores(self, scores_list):
        """
        Upload one or more data quality scores for rule occurrences

        Args:
            scores_list: List of score dictionaries. Format:
                [
                    {
                        "assetId": "rule-occurrence-id",
                        "dqscore": {
                            "facts": {
                                "com.infa.ccgf.models.governance.value": 94,
                                "com.infa.ccgf.models.governance.totalCount": 20000,
                                "com.infa.ccgf.models.governance.exception": 764,
                                "com.infa.ccgf.models.governance.scannedTime": "2022-02-09T10:10:12.441Z"
                            }
                        }
                    }
                ]

        Returns:
            requests.Response: API response
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        if not self.session_id:
            raise Exception("Session ID is not available. Please authenticate first.")

        dq_url = self.base_api_url + '/ccgf-ruleautomation/api/v1/dataQuality/publishScore?refBy=INTERNAL'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json',
            'IDS-SESSION-ID': self.session_id
        }

        body = {
            "scores": scores_list
        }

        self.logger.info(f"Uploading {len(scores_list)} data quality scores")

        response = requests.patch(dq_url, headers=headers, data=json.dumps(body))
        response.raise_for_status()

        return response

    ##########################
    # Enhanced Asset Operations
    ##########################

    def add_data_classification(self, asset_id, classifications, scheme='external'):
        """
        Add data classifications to an asset

        Args:
            asset_id: Asset ID (internal or external based on scheme)
            classifications: List of classification dicts with structure:
                [
                    {"core.externalId": "classification-id", "core.curationStatus": "ACCEPTED"},
                    {"core.externalId": "another-classification-id"}
                ]
            scheme: 'internal' or 'external'

        Returns:
            requests.Response: API response
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        update_url = self.base_api_url + f'/data360/content/v1/assets/{asset_id}?scheme={scheme}'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json'
        }

        body = {
            "operation": "add",
            "segment": "dataClassification",
            "items": classifications
        }

        self.logger.info(f"Adding {len(classifications)} data classifications to asset {asset_id}")

        response = requests.patch(update_url, headers=headers, data=json.dumps(body))
        response.raise_for_status()

        return response

    ##########################
    # Data Quality Rule Occurrences
    ##########################

    def create_dq_rule_occurrence(self, name, description='', measuring_method='TechnicalScript',
                                   threshold=70, target=95, criticality='Medium',
                                   primary_data_element_external_id=None,
                                   reference_id=None):
        """
        Create a Data Quality Rule Occurrence (DQRO) asset via the bulk import endpoint.

        The direct POST /assets endpoint rejects selfAttributes for RuleInstance assets;
        the supported creation path is the import API (same as what the UI uses).

        Args:
            name: Display name for the rule occurrence
            description: Optional description
            measuring_method: API enum value. Use 'TechnicalScript' for Technical Script,
                'InformaticaCloudDataQuality' for IICS DQ rules.
            threshold: Minimum acceptable score (0-100). Default 70.
            target: Target score (0-100). Default 95.
            criticality: 'Low', 'Medium', 'High', or 'Critical'. Default 'Medium'.
            primary_data_element_external_id: core.externalId of the Column to link as
                the Primary Data Element. Format:
                '<catalog-source-id>://<path>~com.infa.odin.models.relational.Column'
            reference_id: Optional custom reference ID (core.externalId). If omitted,
                a unique ID is auto-generated.

        Returns:
            dict: {
                'jobId': str,           # import job ID
                'jobUri': str,          # job monitoring URI
                'reference_id': str     # the reference ID used in the import row
            }
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        import os
        import tempfile
        import uuid

        ref_id = reference_id or f'DQO-DEMO-{uuid.uuid4().hex[:8].upper()}'

        # Build the import CSV row matching the exported RuleInstance template
        row = {
            'core.externalId': ref_id,
            'core.name': name,
            'core.description': description,
            'com.infa.ccgf.models.governance.TechnicalDescription': description or '-',
            'com.infa.ccgf.models.governance.Criticality': criticality,
            'com.infa.ccgf.models.governance.exception': '',
            'com.infa.ccgf.models.governance.exceptionFilePath': '',
            'com.infa.ccgf.models.governance.Frequency': '',
            'com.infa.ccgf.models.governance.MeasuringMethod': measuring_method,
            'com.infa.ccgf.models.governance.ruleInputPortName': '',
            'com.infa.ccgf.models.governance.ruleOutputPortName': '',
            'com.infa.ccgf.models.governance.RuleType': 'Accuracy',
            'com.infa.ccgf.models.governance.scannedTime': '',
            'com.infa.ccgf.models.governance.Target': str(target),
            'com.infa.ccgf.models.governance.TechnicalRuleReference': '',
            'com.infa.ccgf.models.governance.Threshold': str(threshold),
            'com.infa.ccgf.models.governance.thresholdResult': '',
            'com.infa.ccgf.models.governance.totalCount': '',
            'com.infa.ccgf.models.governance.value': '',
            'core.assetLifecycle': 'Draft',
            'Primary Data Element': primary_data_element_external_id or '',
            'Secondary Data Element': '',
            'Stakeholder: Clone of Governance Administrator': '',
            'Stakeholder: Clone of Governance Owner': '',
            'Stakeholder: Governance Administrator': '',
            'Stakeholder Details': '',
            'Stakeholder: Governance Owner': '',
            'Stakeholders Type': '',
            'Submit Ticket': '',
            'HierarchicalPath': name,
            'Operation': 'Create',
        }

        # Write to a temporary XLSX (import API rejects CSV for RuleInstance assets)
        try:
            import openpyxl
        except ImportError:
            raise ImportError("openpyxl is required for DQRO creation: pip install openpyxl")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Data Quality Rule Occurrence'
        ws.append(list(row.keys()))
        ws.append(list(row.values()))

        tmp_xlsx = tempfile.mktemp(suffix='.xlsx')
        try:
            wb.save(tmp_xlsx)
            self.logger.info(f"Creating DQRO '{name}' via import (ref_id={ref_id}, method={measuring_method})")
            result = self.import_assets(tmp_xlsx)
            result['reference_id'] = ref_id
            return result
        finally:
            if os.path.exists(tmp_xlsx):
                os.unlink(tmp_xlsx)

    def find_column_asset(self, column_name):
        """
        Search for a Column asset by name and return the first match.

        Args:
            column_name: Name of the column to search for (e.g., 'firstname')

        Returns:
            dict: Asset hit with 'core.identity', 'core.externalId', and summary fields,
                  or None if not found
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        results = self.search_assets_advanced(
            knowledge_query=column_name,
            filter_spec=[{
                'type': 'simple',
                'attribute': 'core.classType',
                'values': ['com.infa.odin.models.relational.Column']
            }],
            from_offset=0,
            size=1,
            segments='all'
        )

        hits = results.get('hits', [])
        if hits:
            self.logger.info(f"Found column asset '{column_name}': {hits[0].get('core.identity')}")
            return hits[0]

        self.logger.warning(f"No Column asset found for query: '{column_name}'")
        return None

    def set_primary_data_element(self, dqro_id, column_external_id):
        """
        Link a Column asset as the Primary Data Element of a DQRO via PATCH.

        Uses the association type discovered from existing DQROs:
        com.infa.ccgf.models.governance.asscParentDataElementRuleInstance

        Args:
            dqro_id: Internal ID of the DQRO asset
            column_external_id: core.externalId of the column asset. Format:
                '<catalog-source-id>://<path>~com.infa.odin.models.relational.Column'

        Returns:
            requests.Response: API response
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        patch_url = self.base_api_url + f'/data360/content/v1/assets/{dqro_id}?scheme=internal'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json'
        }

        body = {
            'operation': 'add',
            'segment': 'relationship',
            'items': [{
                'association': 'com.infa.ccgf.models.governance.asscParentDataElementRuleInstance',
                'toExternalIdentity': column_external_id
            }]
        }

        self.logger.info(f"Setting Primary Data Element on DQRO {dqro_id} -> {column_external_id}")

        response = requests.patch(patch_url, headers=headers, json=body)
        response.raise_for_status()
        return response

    def get_dq_scores(self, rule_occurrence_id, scheme='INTERNAL', limit=100,
                      timestamp_ge=None, sort='timestamp:DESC'):
        """
        Retrieve data quality score runs for a rule occurrence.

        Args:
            rule_occurrence_id: Internal or external ID of the DQRO
            scheme: 'INTERNAL' or 'EXTERNAL' (external = reference ID)
            limit: Max results to return (1-100, default 100)
            timestamp_ge: Optional ISO 8601 filter, e.g. '2025-01-01T00:00:00.000Z'
            sort: Sort order, e.g. 'timestamp:DESC' or 'timestamp:ASC'

        Returns:
            dict: Response with 'runs' list and 'summary' pagination info
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        scores_url = (
            self.base_api_url
            + f'/data360/data-quality/v1/rule-occurrences/{rule_occurrence_id}/runs'
            + f'?scheme={scheme}&limit={limit}&sort={sort}'
        )

        if timestamp_ge:
            scores_url += f'&filter=timestamp:GE:({timestamp_ge})'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id
        }

        self.logger.info(f"Getting DQ scores for DQRO: {rule_occurrence_id}")

        response = requests.get(scores_url, headers=headers)
        response.raise_for_status()

        return response.json()

    def add_custom_attributes(self, asset_id, custom_attrs, scheme='external'):
        """
        Add custom attribute values to an asset

        Args:
            asset_id: Asset ID (internal or external based on scheme)
            custom_attrs: Dictionary of custom attribute keys and values
                Example: {"com.infa.odin.models.custom.ca_6004001966368974780": "My Value"}
            scheme: 'internal' or 'external'

        Returns:
            requests.Response: API response
        """
        if not self.jwt_token:
            raise Exception("JWT Token is not available. Please authenticate first.")

        update_url = self.base_api_url + f'/data360/content/v1/assets/{asset_id}?scheme={scheme}'

        headers = {
            'Authorization': 'Bearer ' + self.jwt_token,
            'X-INFA-ORG-ID': self.org_id,
            'Content-Type': 'application/json'
        }

        body = {
            "operation": "add",
            "segment": "customAttributes",
            "attributes": custom_attrs
        }

        self.logger.info(f"Adding custom attributes to asset {asset_id}")

        response = requests.patch(update_url, headers=headers, data=json.dumps(body))
        response.raise_for_status()

        return response
