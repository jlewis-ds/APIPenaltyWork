# APIPenaltyWork
 Collection and analysis of NHL games through the public API. All links need to concat the base API string in order to return a real result.
 
 Functions thus far:
 
 scheduleOpener(start, end) - returns a dataframe containing high level information about every game in the timespan provided. This is where links to games can be found.
 
 loadGamePlays(gamelink) - returns a tuple with (json, hometeam, awayteam) where the json contains every play recorded as an event.
 
 gamePenaltyDf(loadGamePlaysOutput) - this takes the tuple of (json, home code, away code) and builds a dataframe containing only the penalties in the game, as well as several calculated columns to be used for further analysis.
 
 ...
