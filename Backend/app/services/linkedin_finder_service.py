import os
import requests
import urllib.parse
from typing import Optional, Dict, Any
from supabase import Client

class LinkedInFinder:
    """
    A service class to find LinkedIn URLs for candidates using the PDL API.
    """
    def __init__(self):
        """
        Initializes the LinkedInFinder.
        Checks for the PDL API key upon instantiation.
        """
        self.pdl_api_key = os.getenv('PDL_API_KEY')
        if self.pdl_api_key:
            print("LinkedInFinder initialized with PDL API key.")
        else:
            print("LinkedInFinder initialized without PDL API key. LinkedIn search will not work.")

    def _normalize_linkedin_url(self, url: Optional[str]) -> Optional[str]:
        """
        Cleans and standardizes a LinkedIn URL.
        """
        if not url:
            return None
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        # Strip query params and trailing slash for cleanliness
        url = url.split('?')[0].rstrip('/')
        return url

    def _conservative_name_split(self, full_name: str) -> (str, str):
        """Splits a full name into first and last name parts."""
        parts = full_name.strip().split()
        if len(parts) == 0:
            return "", ""
        if len(parts) == 1:
            return "", parts[0]
        return " ".join(parts[:-1]), parts[-1]

    def _enrich_with_pdl(self, first_name: str, last_name: str, company: str, title: str) -> Optional[str]:
        """
        Enriches a profile using the PDL API to find a LinkedIn URL.
        """
        if not self.pdl_api_key:
            print("PDL API key not found. Cannot perform enrichment.")
            return None

        params = {"api_key": self.pdl_api_key}
        if first_name:
            params["first_name"] = first_name
        if last_name:
            params["last_name"] = last_name
        if company:
            params["company"] = company
        if title:
            params["title"] = title
        
        try:
            url = "https://api.peopledatalabs.com/v5/person/enrich" + "?" + urllib.parse.urlencode(params)
            response = requests.get(url, timeout=30)
            
            if response.status_code == 404:
                print("PDL returned 404 - No match found.")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            # Extract LinkedIn URL from the response
            return self._extract_linkedin_from_pdl_response(data)

        except requests.HTTPError as e:
            print(f"PDL HTTP error: {e.response.status_code} {e.response.text}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during PDL enrichment: {e}")
            return None

    def _extract_linkedin_from_pdl_response(self, resp: Dict[str, Any]) -> Optional[str]:
        """
        Extracts the LinkedIn URL from a PDL API response.
        """
        if not isinstance(resp, dict):
            return None

        person = resp.get("data") if isinstance(resp.get("data"), dict) else resp

        for key in ("linkedin_url", "linkedin", "linkedin_profile", "linkedin_profile_url"):
            v = person.get(key)
            if isinstance(v, str) and v and "linkedin" in v:
                return self._normalize_linkedin_url(v)

        for arr_key in ("profiles", "social_profiles", "social"):
            arr = person.get(arr_key)
            if isinstance(arr, list):
                for p in arr:
                    if not isinstance(p, dict):
                        continue
                    network = str(p.get("network") or p.get("type") or "").lower()
                    url = p.get("url") or p.get("profile_url") or p.get("original_url")
                    if isinstance(url, str) and "linkedin" in (url.lower() or network):
                        return self._normalize_linkedin_url(url)
                    username = p.get("username")
                    if network and "linkedin" in network and username:
                        return self._normalize_linkedin_url(f"linkedin.com/in/{username}")

        return None

    def find_and_update_url(self, profile_id: str, supabase: Client) -> Optional[str]:
        """
        The main public method for this service. It fetches candidate data,
        finds the URL using the PDL API, and updates the database.
        """
        try:
            profile_res = supabase.table("search").select("profile_name, company, role").eq("profile_id", profile_id).single().execute()

            if not profile_res.data:
                print(f"No profile found with profile_id: {profile_id}")
                return None

            profile = profile_res.data
            candidate_name = profile.get("profile_name")
            current_company = profile.get("company")
            current_title = profile.get("role")
            
            if not candidate_name:
                print(f"Candidate {profile_id} is missing a name. Cannot search.")
                return None

            first_name, last_name = self._conservative_name_split(candidate_name)

            # Use the PDL enrichment logic
            linkedin_url = self._enrich_with_pdl(first_name, last_name, current_company, current_title)

            if linkedin_url:
                print(f"URL found for {candidate_name}: {linkedin_url}. Updating database.")
                # Update the ranked_candidates table as per the previous logic
                (supabase.table("ranked_candidates")
                  .update({"linkedin_url": linkedin_url})
                  .eq("profile_id", profile_id)
                  .execute())
                return linkedin_url
            else:
                print(f"LinkedIn URL not found for {candidate_name}.")
                return None

        except Exception as e:
            print(f"An unexpected error occurred in find_and_update_url: {e}")
            return None