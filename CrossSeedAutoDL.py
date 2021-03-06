#! Python 3.6

import json
import os
import re
import requests
import shutil
from ctypes import windll, wintypes

############################
# edit these variables as it applies to your working environment

# path to download torrents into
DOWNLOAD_PATH = ''
# jackett api key
API_KEY = ''
# the parent folder whose child files/folders names will be used to conduct the search
MAIN_FOLDER = ''

# tracker (which has been added to your Jackett as an indexer) in which to search for cross-seedable torrents
TRACKER = 'blutopia'
JACKETT_URL = 'http://127.0.0.1'
JACKETT_PORT = '9117'

############################

TITLES_NOT_FOUND_JSON = './TITLES_NOT_FOUND.json'

SEARCH_STRING_START = '/api/v2.0/indexers/all/results?apikey='
SEARCH_STRING_MIDDLE = '&Query='
SEARCH_STRING_END = '&Tracker%5B%5D='

AKA_DUAL_LANG_NAME_RE = r'(.+?)\baka\b(.+)'

TITLE_RE = r'(.+?)(\b(\d{4}|\d+p)\b|\b(season|s).?\d+)\b'
YEAR_RE = r'.+\b((?:19|20)\d\d)\b'
EDITION_RE = r'(tvdb order|remaster|imax|proper|repack|internal|EXTENDED|UNRATED|DIRECTORS?|COLLECTORS?)(ed)?(.CUT)?'
GROUP_RE = r'- ?([^\.\s]+) *(\[.+?\])? *(\.\w+)?$'

FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
GetFileAttributes = windll.kernel32.GetFileAttributesW


def main():
	titlesNotFound = []
	pathListings = os.listdir(MAIN_FOLDER)

	for i, listing in enumerate(pathListings):
		listingPath = os.path.join(MAIN_FOLDER, listing)
		if not os.path.isdir(listingPath):
			continue

		group = getGroupName(listing)
		title = listing
		m = re.search(TITLE_RE, title, re.IGNORECASE)
		if m: title = m.group(1)

		year = ''
		m = re.search(YEAR_RE, listing)
		if m: year = m.group(1)

		title = re.sub(r'\'s\b', ' ', title, flags=re.IGNORECASE)
		title = re.sub(r'\s+', ' ', title, flags=re.IGNORECASE)
		title = re.sub(EDITION_RE, ' ', title, flags=re.IGNORECASE)
		title = re.sub(r'[\W_]', ' ', title)
		
		# print(title)
		pathSize = get_size(listingPath)
		if pathSize == None:
			continue

		queries = []
		if re.search(AKA_DUAL_LANG_NAME_RE, title, re.IGNORECASE):
			editedTitle = re.sub(AKA_DUAL_LANG_NAME_RE, r'\1', title, flags=re.IGNORECASE) + f' {year} {group}'
			queries.append(editedTitle)
			editedTitle = re.sub(AKA_DUAL_LANG_NAME_RE, r'\2', title, flags=re.IGNORECASE) + f' {year} {group}'
			queries.append(editedTitle)
		else:
			queries.append(f'{title} {year} {group}')

		print(f'Searching for {i+1} of {len(pathListings)}:\t{queries}\t{[listing]}')
		# print(queries, '\t\t\t', listing, '\n');continue
		for query in queries:
			query = '%20'.join(query.split())
			# query = re.sub(r'\'', '%27', query)

			searchURL = f'{JACKETT_URL}:{JACKETT_PORT}{SEARCH_STRING_START}{API_KEY}{SEARCH_STRING_MIDDLE}{query}{SEARCH_STRING_END}{TRACKER}'
			source = requests.get(searchURL).text
			returnedJSON = json.loads(source)
			print([f['Title'] for f in returnedJSON['Results']]); print('');continue

			found = findMatchingTorrent(returnedJSON, pathSize, listingPath)
			if found == False:
				titlesNotFound.append(listing)

	with open(TITLES_NOT_FOUND_JSON, 'w', encoding='utf8') as f:
		json.dump(titlesNotFound, f, indent=4)


def get_size(path):
	tempPath = path
	if os.path.isfile(path):
		return get_file_size(path)
	elif os.path.isdir(path):
		totalSize = 0
		for root, dirs, filenames in os.walk(path):
			for filename in filenames:
				filesize = get_file_size(os.path.join(root, filename))
				if filesize == None:
					return None
				totalSize += filesize
		return totalSize
	return None

def get_file_size(filepath):
	if islink(filepath):
		targetPath = os.readlink(filepath)
		if os.path.isfile(targetPath):
			return os.path.getsize(targetPath)
	else:
		return os.path.getsize(filepath)
	return None


def islink(filepath):
    # assert os.path.isdir(filepath), filepath
    if GetFileAttributes(filepath) & FILE_ATTRIBUTE_REPARSE_POINT:
        return True
    else:
        return False


def validatePath(filepath):
	path_filename, ext = os.path.splitext(filepath)
	n = 1

	if not os.path.isfile(filepath):
		return filepath

	filepath = f'{path_filename} ({n}){ext}'
	while os.path.isfile(filepath):
		n += 1
		filepath = f'{path_filename} ({n}){ext}'

	return filepath


def getGroupName(releaseName):
	m = re.search(GROUP_RE, releaseName)
	if m:
		return m.group(1)
	return ''


def findMatchingTorrent(returnedJSON, pathSize, listingPath):
	MB = 1000000
	MAX_FILESIZE_DIFFERENCE = 10 * MB
	if os.path.isfile(listingPath) and pathSize < 1000 * MB:
		MAX_FILESIZE_DIFFERENCE = 0.01 * MB
	found = False
	for result in returnedJSON['Results']:
		listingTitle = result['Title']
		downloadURL = result['Link']
		listingSize = result['Size']

		# if size difference is less than the below referenced number of bytes, download torrent
		if abs(pathSize - listingSize) <= MAX_FILESIZE_DIFFERENCE:
			found = True
			print('  >> Found possible match. Downloading\n')
			downloadTorrent(downloadURL, listingTitle)
	return found


def downloadTorrent(downloadURL, torrentName):
	torrentName = re.sub(r'[<>:\"/\\?*\|]+', '', torrentName)

	response = requests.get(downloadURL, stream=True)
	projectedPath = os.path.join(DOWNLOAD_PATH, f'{torrentName}.torrent')
	downloadPath = validatePath(projectedPath)

	with open(downloadPath, 'wb') as f:
	    shutil.copyfileobj(response.raw, f)


if __name__ == '__main__':
	main()
