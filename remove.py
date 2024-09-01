import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import inquirer
import pytz
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('REFRESH_TOKEN')

def get_access_token(client_id, client_secret, refresh_token):
    url = "https://accounts.spotify.com/api/token"
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    auth = HTTPBasicAuth(client_id, client_secret)  # Basic auth for Spotify API
    response = requests.post(url, data=data, auth=auth)
    if response.status_code == 200:
        print("Successfully obtained access token.")
        return response.json()['access_token']  # Return the new access token
    else:
        print(f"Failed to get access token. Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return None

def get_saved_episodes(access_token):
    url = "https://api.spotify.com/v1/me/episodes"
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    episodes = []
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            episodes.extend(data['items'])  # Append fetched episodes to our list
            url = data['next']
        else:
            print(f"Failed to fetch saved episodes. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            break
    print(f"Total episodes fetched: {len(episodes)}")
    return episodes

def get_unique_authors(episodes):
    authors = set()
    for ep in episodes:
        authors.add(ep['episode']['show']['publisher'])  # Add each unique publisher to a set
    return sorted(authors)

def remove_saved_episode(access_token, episode_id):
    url = f"https://api.spotify.com/v1/me/episodes?ids={episode_id}"
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.delete(url, headers=headers)
    return response.status_code

def remove_episodes_by_date(episodes, date_type, before_date, local_tz, selected_authors=None):
    before_date_obj = datetime.strptime(before_date, '%Y-%m-%d')
    before_date_obj = local_tz.localize(before_date_obj) # Convert the before_date to a timezone-aware datetime
    filtered_episodes = []

    if not selected_authors:
        print("No authors selected, please select at least one author.")
        return filtered_episodes

    for ep in episodes:
        episode_title = ep['episode']['name']
        podcast_name = ep['episode']['show']['name']
        podcast_author = ep['episode']['show']['publisher']

        if podcast_author not in selected_authors:
            continue # Skip episodes that don't match the selected authors

        # Determine the date type for filtering
        if date_type == 'Date Added to Library':
            episode_date = datetime.strptime(ep['added_at'], '%Y-%m-%dT%H:%M:%SZ')
            date_label = "Date Added to Library"
        elif date_type == 'Podcast Release Date':
            episode_date = datetime.strptime(ep['episode']['release_date'], '%Y-%m-%d')
            date_label = "Podcast Release Date"
        
        # Convert episode date to the local timezone
        episode_date = pytz.utc.localize(episode_date).astimezone(local_tz)
        
        if episode_date < before_date_obj:
            filtered_episodes.append(ep)
            print(f"Test mode: Would remove episode '{episode_title}' from podcast '{podcast_name}' by '{podcast_author}' ({date_label}: {episode_date.strftime('%Y-%m-%d %H:%M:%S %Z')})")

    print(f"Total episodes matching criteria: {len(filtered_episodes)}")
    return filtered_episodes

# Main function to run the episode removal process based on user input
def remove_episodes_based_on_filter(test_mode=True, date_type='Date Added to Library', before_date=None, local_tz=pytz.utc, selected_authors=None):
    access_token = get_access_token(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
    if access_token is None:
        print("Exiting script due to failure in obtaining access token.")
        return
    
    episodes = get_saved_episodes(access_token)
    if not episodes:
        print("No episodes were returned.")
        return

    if before_date:
        episodes_to_remove = remove_episodes_by_date(episodes, date_type, before_date, local_tz, selected_authors)

    # If not in test mode, actually remove the episodes
    if not test_mode and episodes_to_remove:
        for episode in episodes_to_remove:
            episode_id = episode['episode']['id']
            status = remove_saved_episode(access_token, episode_id)
            if status == 200:
                print(f"Removed episode '{episode['episode']['name']}' from podcast '{episode['episode']['show']['name']}'")
            else:
                print(f"Failed to remove episode '{episode['episode']['name']}' from podcast '{episode['episode']['show']['name']}'")

# Entry point of the script, handling user input and invoking the main process
if __name__ == "__main__":
    common_timezones = [
        ("UTC (Coordinated Universal Time)", "UTC"),
        ("America/New_York (EST, UTC-5)", "America/New_York"),
        ("America/Los_Angeles (PST, UTC-8)", "America/Los_Angeles"),
        ("Europe/London (BST, UTC+1)", "Europe/London"),
        ("Europe/Paris (CET, UTC+2)", "Europe/Paris"),
        ("Asia/Tokyo (JST, UTC+9)", "Asia/Tokyo"),
        ("Australia/Sydney (AEST, UTC+10)", "Australia/Sydney"),
        ("Asia/Hong_Kong (HKT, UTC+8)", "Asia/Hong_Kong"),
        ("Asia/Kolkata (IST, UTC+5:30)", "Asia/Kolkata")
    ]

    # Initial setup to fetch episodes and extract authors
    access_token = get_access_token(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)

    if access_token:
        # Get unique authors from saved episodes
        episodes = get_saved_episodes(access_token)
        authors = get_unique_authors(episodes)
        authors.insert(0, "Select All")
        selected_authors = inquirer.prompt([inquirer.Checkbox(
            'authors',
            message="Select author(s) to filter episodes by (use spacebar to select, enter to confirm):",
            choices=authors,
        )])['authors']
        
        # Automatically select all if the user didn't select anything
        if not selected_authors or "Select All" in selected_authors:
            selected_authors = authors[1:]
            print("Automatically selecting all authors as none were explicitly selected.")

    else:
        print("Failed to authenticate with Spotify.")
        exit()

    # Asking the user for more specific filtering options
    questions = [
        inquirer.List('date_type',
                      message="Choose the date type for filtering episodes",
                      choices=['Date Added to Library', 'Podcast Release Date'],
                      ),
        inquirer.Text('before_date',
                      message="Enter the date (YYYY-MM-DD) to remove episodes before this date"),
        inquirer.List('timezone',
                      message="Select your timezone",
                      choices=[tz[0] for tz in common_timezones],
                      ),
        inquirer.Confirm('test_mode',
                         message="Run in test mode (no episodes will be removed)?",
                         default=True),
    ]

    # Capture the user's responses
    answers = inquirer.prompt(questions)
    local_tz = pytz.timezone(dict(common_timezones)[answers['timezone']])

    # Running the filtering/removal process based on user input
    print(f"Running with the following options: Date Type = {answers['date_type']}, Before Date = {answers['before_date']}, Test Mode = {answers['test_mode']}, Timezone = {answers['timezone']}, Authors = {selected_authors}")
    remove_episodes_based_on_filter(test_mode=answers['test_mode'], date_type=answers['date_type'], before_date=answers['before_date'], local_tz=local_tz, selected_authors=selected_authors)