#!/usr/bin/env python
# coding: utf-8

import sys
import os
import urllib
import json
import re
import pandas as pd
import numpy as np
import seaborn as sns
import itertools

#Open schedule between start and end date (format YYYY-MM-DD)
def scheduleOpener(start, end):
    """Date format: 'YYYY-MM-DD'
    
    Returns a dataframe containing information for every game within
    the dates provided.
    """
    #Confirm start/end is in string format
    start = str(start)
    end = str(end)
    
    #Access the API endpoint for the schedule
    schedule = urllib.request.urlopen('https://statsapi.web.nhl.com/api/v1/schedule?startDate=%s&endDate=%s' % (start, end))
    
    #Load the data in with json.loads
    scheduledata = json.loads(schedule.read().decode(schedule.info().get_param('charset') or 'utf-8'))
    
    season = pd.io.json.json_normalize(scheduledata, record_path = ['dates', 'games'])
    
    #Subset the data for only regular and playoff games
    season = season[(season['gameType'] == 'R') | (season['gameType'] == 'P')]
    
    #Clean up the index after the subsetting
    season.reset_index(drop=True, inplace=True)
    
    return season


#Load all the plays within the provided game link
def loadGamePlays(gamelink):
    """This takes links from cleanSeasonDf['link'].
    Open up a link to a game to get every play that occurred. Returns a tuple
    with (plays - df, homeTeam - triCode for home team, awayTeam - triCode for away team)"""
    
    #Open a game link
    game = urllib.request.urlopen(base+gamelink)
    gamedata = json.loads(game.read().decode(game.info().get_param('charset') or 'utf-8'))

    #Grab the data about every play that happened
    plays = gamedata['liveData']['plays']['allPlays']
    
    #Also grab the tricodes for the involved teams for future use
    homeTeam = gamedata['gameData']['teams']['home']['triCode']
    awayTeam = gamedata['gameData']['teams']['away']['triCode']
    
    return (plays, homeTeam, awayTeam)

def winningTeamPenalty(r):
    """Small helper function for gamePenaltyDf. Creates a new column which indicates if the 
    team who was winning at the time of a penalty is the one who took it"""
    
    #Check if home or away had more goals at the 'event' time
    homecheck = int(r['about.goals.home'] > r['about.goals.away'])
    awaycheck = int(r['about.goals.away'] > r['about.goals.home'])
    
    #If home had more goals and the penalty was on the home team, set to 1
    if (homecheck > 0) and (r['against.homeTeam'] == 1):
        return 1
    #If away had more and the penalty was not on home team, set to 1
    if (awaycheck > 0) and (r['against.homeTeam'] == 0):
        return 1
    #Any other situation should be a zero in this column
    else:
        return 0

def gamePenaltyDf(plays_home_away):
    """This takes output from loadGamePlays.
    Creates a df from all the plays in a game, then cleans up to only look at penalties. The resulting
    penalties df is then reduced only relevant columns, and the results are
    returned along with newly calculated columns.
    
    If there are no penalties to find we return 0"""
    
    #Load the read plays data into a dataframe
    playsdf = pd.io.json.json_normalize(plays_home_away[0])
    #Also grab the tricodes
    home_tricode = plays_home_away[1]
    away_tricode = plays_home_away[2]
    
    #Define the columns I want from the data
    relevant_columns = ['about.dateTime', 'about.eventId', 'about.goals.away', 'about.goals.home', 'about.period', 'about.periodTimeRemaining', 'result.penaltyMinutes', 'result.penaltySeverity', 'result.secondaryType', 'team.triCode']
    #Confirm that there are actually penalty minutes in the game
    if 'result.penaltyMinutes' in list(playsdf.columns):
        #Subset down to only plays which resulted in non-nan penalty minutes
        pdf = playsdf[playsdf['result.penaltyMinutes'].isna()==False]
        pdf.reset_index(drop=True, inplace=True)
        #Reduce the columns down to the relevant ones
        relevantdf = pdf[relevant_columns].copy()
        #Some manufactured columns
        relevantdf['against.homeTeam'] = relevantdf['team.triCode'].apply(lambda code: int(code == home_tricode))
        relevantdf['against.awayTeam'] = relevantdf['team.triCode'].apply(lambda code: int(code == away_tricode))
        relevantdf['committed.playingAgainst'] = relevantdf['team.triCode'].apply(lambda code: away_tricode if code == home_tricode else home_tricode)
        relevantdf['winning.teamPenalty'] = relevantdf.apply(lambda x: winningTeamPenalty(x), 1)
        #Markov Chain type columns - recording the state of the game and most recent state
        relevantdf['prev.against.home'] = relevantdf['against.homeTeam'].shift(1).fillna(0)
        relevantdf['prev.against.away'] = relevantdf['against.awayTeam'].shift(1).fillna(0)
        relevantdf['goal.diff'] = relevantdf['about.goals.home'] - relevantdf['about.goals.away']
        relevantdf['penalty.diff'] = relevantdf['against.homeTeam'].cumsum() - relevantdf['against.awayTeam'].cumsum()
        
        return relevantdf
    else:
        return 0
    
def updatePenaltyDf(temp_df, season, end):
    """Take in an existing df and updates it. Uses loadGamePlays, gamePenaltyDf and then appends
    the results to the provided df. End defines the game in the season at which
    to end the update. Season should be a cleanSeasonDf which has a column of 'links'."""
    
    #If the temp_df is empty, we start at game 0
    if np.nan_to_num(temp_df['gameNumber'].max()) == 0:
        start = 0
    else:
        #If it's not empty we start at the last game entered
        start = int(temp_df['gameNumber'].max())
        end = int(end)
        #Also confirm that we know what the last timestamp was to prevent duplication
        last_timestamp = temp_df.iloc[-1]['about.dateTime']
        
    for n in range(start, end):
        #Load the plays from games between start and the given end value
        plays_home_away = loadGamePlays(season['link'][n])
        #The result is the penalty df 
        result = gamePenaltyDf(plays_home_away)
        
        #If we are updating from the beginning of a previous df, and we aren't on the first game
        #then we make sure the event is later than the last one defined. Prevent's duplication.
        if (n == start) and (n > 0):
            result = result[result['about.dateTime'] > last_timestamp]
        
        #If result gets a 0 (no penalties in the game)
        if type(result) == int:
            #Just continue
            continue
        else:
            #Create a column for which game number the results are from
            game_number = [n]*len(result)
            #Also provide what type of game it was (R/P)
            game_type = [season['gameType'][n]]*len(result)
            result['regular.playoffs'] = game_type
            result['gameNumber'] = game_number
            #Append the results from the game to the provided temporary dataframe
            temp_df = temp_df.append(result)
    
    #Reset the index at the end since we've appended several together
    temp_df.reset_index(drop=True, inplace=True)
    
    #Create a copy of the result and return it
    updated_df = temp_df.copy()
    return updated_df


# In[ ]:


def pensPerGameAgainst(team1, team2, df, include_playoffs=True, only_playoffs=False):
    
    #Convert triCodes to strings
    t1 = str(team1)
    t2 = str(team2)
    
    #Should playoffs be included
    if include_playoffs == False:
        df = df[df['regular.playoffs'] == 'R']
    if only_playoffs == True:
        df = df[df['regular.playoffs'] == 'P']
    
    #Group up based on who took the penalty and who it was against
    grouping = df[['team.triCode', 'committed.playingAgainst', 'gameNumber', 'result.secondaryType']].groupby(['team.triCode', 'committed.playingAgainst'])
    
    #Grab the subset matching the requested teams
    team_vs_team = grouping.get_group((t1, t2))
    
    #Get the value counts and unique game numbers
    pens_and_counts = team_vs_team['result.secondaryType'].value_counts()
    per_game_pens_and_counts = pens_and_counts/team_vs_team['gameNumber'].nunique()
    penalties = pens_and_counts.keys().tolist()
    counts = pens_and_counts.values
    per_game_counts = per_game_pens_and_counts.values
    
    #Get league wide per game values
    league = df['result.secondaryType'].value_counts()/df['gameNumber'].nunique()
    included_penalties = [i for i in league.items() if i[0] in penalties]
    league_dict = dict(included_penalties)
    #Subtract per game values for the paired up teams -> distance from league average
    for tup in per_game_pens_and_counts.items():
        league_dict[tup[0]] = tup[1] - league_dict[tup[0]] 
    
    #Create the plots
    fig, ax = plt.subplots(ncols=2, figsize=(12,6), sharey=False)

    pergame = sns.barplot(x=per_game_counts, y=penalties, color='steelblue', alpha=0.8, 
                          edgecolor=".2", dodge=True, ax=ax[0])
    for p in ax[0].patches:
        width = p.get_width()
        ax[0].text(width, p.get_y()+p.get_height()/2. + 0.2,
                '{:1.2f}'.format(width),
                ha="left")
    
    #League comparison
    league_df = pd.DataFrame.from_dict(league_dict, orient='index').reset_index()
    league_df.columns = ['Penalty', 'Relative to League']
    #league_df['color'] = league_df['Relative to League'].apply(lambda v: 'g' if v > 0.0 else 'r')
    #print(league_df)
    league_comp = sns.barplot(x=league_df['Relative to League'], y=league_df['Penalty'], edgecolor=".2",
                            ax=ax[1])
    for p in ax[1].patches:
        width = p.get_width()
        ax[1].text(width, p.get_y()+p.get_height()/2. + 0.2,
                '{:1.2f}'.format(width),
                ha="left")
    
    plt.tight_layout()
    return team_vs_team['gameNumber'].nunique()

