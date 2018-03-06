
from __future__ import print_function
import csv
import os

import numpy as np
import tables as tb

from pyne import nucname
from pyne.api import nuc_data
from pyne.dbgen.api import BASIC_FILTERS


def grab_dose_factors():
    """Parses data from dose factor csv files.
    """
    
    # Populates Dose Factor list with initial set of energies: opens .csv file and parses it
    dose_factors = []
    with open(os.path.join(os.path.dirname(__file__), 'ICRP74.csv'), 'r') as f:
        reader = csv.reader(f)
        next(f)
        de_df = [] 
        for row in reader:           
            de = float(row[0])
            df = float(row[1])
            de_df = [de, df]
            dose_factors.append(de_df)
    return dose_factors

def make_dose_tables(dose_factors, nuc_data, build_dir=""):
    """Adds three dose factor tables to the nuc_data.h5 library.

    Parameters
    ----------
    genii: list of tuples
        Array of dose factors calculated by the code GENII.
    nuc_data : str
        Path to nuclide data file.
    build_dir : str
        Directory to place q_value files in.
    """
    
    # Define data types for all three cases
    dose_dtype = np.dtype([
        ('de', float),
        ('df', float),
        ])

    # Convert to numpy arrays
    icrp74_array = np.array(dose_factors, dtype=dose_dtype)

    # Open the hdf5 file
    nuc_file = tb.open_file(nuc_data, 'a', filters=BASIC_FILTERS)

    # Create a group for the tables
    dose_group = nuc_file.create_group("/", "dose_conversion_factors", "Dose Conversion Factors")

    # Make new table
    icrp74_table = nuc_file.create_table(dose_group, 'ICRP74', icrp74_array, 'de [MeV], df [Sv/s]')

    # Ensure that data was written to table
    icrp74_table.flush()

    # Close the hdf5 file
    nuc_file.close()

def make_dose_factors(args):
    """Controller function for adding dose conversion factors"""

    nuc_data, build_dir = args.nuc_data, args.build_dir
    if os.path.exists(nuc_data):
        with tb.open_file(nuc_data, 'r') as f:
            if '/dose_conversion_factors' in f:
                print("skipping creation of dose conversion factor tables; already exists.")
                return
    
    # Grab the dose factors from each file
    print('Grabbing dose conversion factors...')
    dose_factors = grab_dose_factors()

    # Make the 3 dose factor tables and writes them to file
    print("Making dose conversion factors tables...")
    make_dose_tables(dose_factors, nuc_data, build_dir)
