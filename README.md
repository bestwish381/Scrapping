# Vinted Scraper configuration

## Information
This repository contains the configuration of the Vinted Scraper project. The default Ubuntu 24.04 LTS environment comes with Python 3.12.3 installed. The configuration of the environment is described below. 

## Configuration of the Ubuntu 24.04 LTS environment (Amazon AWS)
1. `sudo apt-get update` - This command updates the package list.
2. `sudo apt-get upgrade -y` - This command upgrades the packages.
3. `sudo apt-get install python3-pip -y` - This command installs the Python package manager.
4. `sudo apt-get install python3-venv -y` - This command installs the Python virtual environment package.
5. Copy the files towards the Ubuntu environment and navigate to the directory where the files are located.
5. `python3 -m venv venv` - This command creates a virtual environment.
6. `source venv/bin/activate` - This command activates the virtual environment.
7. `pip install -r requirements.txt` - This command installs the required packages.

## Running the Vinted Scraper
1. Copy the files towards the Ubuntu environment and navigate to the directory where the files are located.
2. `source venv/bin/activate` - This command activates the virtual environment.
3. `python main.py` - This command runs the Vinted Scraper.

## Additional information (can be re-used to retrieve size_ids and brand_ids) 
# https://www.vinted.co.uk/catalog?size_ids[]=207&size_ids[]=208&size_ids[]=209&size_ids[]=210&size_ids[]=211&size_ids[]=212&brand_ids[]=53&brand_ids[]=14&brand_ids[]=162&brand_ids[]=21099&brand_ids[]=345&brand_ids[]=245062&brand_ids[]=359177&brand_ids[]=484362&brand_ids[]=313669&brand_ids[]=8715&brand_ids[]=378906&brand_ids[]=140618&brand_ids[]=1798422&brand_ids[]=597509&brand_ids[]=1065021&brand_ids[]=57144&brand_ids[]=345731&brand_ids[]=269830&brand_ids[]=99164&brand_ids[]=73458&brand_ids[]=670432&brand_ids[]=719079&brand_ids[]=299684&brand_ids[]=1985410&brand_ids[]=311812&brand_ids[]=291429&brand_ids[]=1037965&brand_ids[]=472855&brand_ids[]=511110&brand_ids[]=299838&brand_ids[]=8139&brand_ids[]=401801&brand_ids[]=3063&brand_ids[]=1412112&brand_ids[]=164166&brand_ids[]=190014&brand_ids[]=46923&brand_ids[]=506331&brand_ids[]=13727&brand_ids[]=345562&brand_ids[]=335419&brand_ids[]=318349&brand_ids[]=276609&order=newest_first
