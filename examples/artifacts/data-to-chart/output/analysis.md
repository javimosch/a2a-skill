# Data Analysis Report

Analysis of generated datasets with statistical summaries and ASCII charts.

## Datasets

### CPU Temperature (°C) over 30 time points

| Metric | Value |
|--------|-------|
| Data Points | 30 |
| Minimum | 38.60 |
| Maximum | 75.60 |
| Mean | 58.05 |
| Median | 60.70 |
| Std Deviation | 11.07 |
| Range | 37.00 |
| Trend | decreasing |
| Volatility | 4.40 |

```
 CPU Temperature (°C) over 30 time points
 Range: 38.6 to 75.6

    75.6 |         *                    
    70.3 |      *   **                  
    65.0 |   * *  *   ****              
    59.7 | *  *  *        **            
    54.5 |* *               **          
    49.2 |                    * *       
    43.9 |                     *  * *   
    38.6 |                       * * ***
          +----------------------------+
           0    5    10    15    20    25   29
           Data points: 0 to 29 (n=30)

  Statistics
    Min: 38.60
    Max: 75.60
    Mean: 58.05
    Range: 37.00
    Trend: 📉 Decreasing
```

### Server Response Time (ms) over 25 samples

| Metric | Value |
|--------|-------|
| Data Points | 25 |
| Minimum | 83.10 |
| Maximum | 334.40 |
| Mean | 150.10 |
| Median | 138.70 |
| Std Deviation | 63.71 |
| Range | 251.30 |
| Trend | decreasing |
| Volatility | 63.92 |

```
 Server Response Time (ms) over 25 samples
 Range: 83.1 to 334.4

   334.4 |  *                      
   298.5 |                         
   262.6 |                  *   *  
   226.7 |                         
   190.8 |                         
   154.9 |    ** ***              *
   119.0 | * *  *   ***            
    83.1 |*            ***** *** * 
          +-----------------------+
           0   4   8   12   16   20   24
           Data points: 0 to 24 (n=25)

  Statistics
    Min: 83.10
    Max: 334.40
    Mean: 150.10
    Range: 251.30
    Trend: 📉 Decreasing
```

### Daily Active Users over 30 days

| Metric | Value |
|--------|-------|
| Data Points | 30 |
| Minimum | 981.00 |
| Maximum | 1161.00 |
| Mean | 1071.07 |
| Median | 1069.00 |
| Std Deviation | 48.47 |
| Range | 180.00 |
| Trend | increasing |
| Volatility | 31.14 |

```
 Daily Active Users over 30 days
 Range: 981.0 to 1161.0

  1161.0 |                       *      
  1135.3 |                      *      *
  1109.6 |               **       *   * 
  1083.9 |         *       *   *   *    
  1058.1 |        * *   *   *        *  
  1032.4 | ***   *   *        *     *   
  1006.7 |    *       **     *          
   981.0 |*    **                       
          +----------------------------+
           0    5    10    15    20    25   29
           Data points: 0 to 29 (n=30)

  Statistics
    Min: 981.00
    Max: 1161.00
    Mean: 1071.07
    Range: 180.00
    Trend: 📈 Increasing
```

## Methodology

- **CPU Temperature**: Synthetic data modeling a server CPU with diurnal cycles and occasional thermal spikes.
- **Response Time**: Server response times with increasing baseline load and outlier spikes.
- **Daily Active Users**: Growth trend with weekly seasonality patterns.

ASCII charts rendered at 50-character width with 8-row height.

*This report was generated from synthesized data. Agents were unable to participate due to API key limits; the build script produced this directly as a fallback.*