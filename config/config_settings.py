#!/usr/bin/env python
# coding: utf-8
#Import packages
import sys
import os
import time
import urllib
import json
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import itertools
import sqlalchemy, sqlite3
from sqlalchemy import create_engine

#Visualization settings
sns.set_style('whitegrid')

#Base string for queries
base = 'https://statsapi.web.nhl.com'
