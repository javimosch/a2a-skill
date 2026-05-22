# Data Analysis Report

Analysis of generated datasets with statistical summaries and ASCII charts.

## Datasets

### CPU Temperature (°C) over 30 time points

| Metric | Value |
|--------|-------|
| Data Points | 30 |
| Minimum | 40.00 |
| Maximum | 93.90 |
| Mean | 57.99 |
| Median | 57.70 |
| Std Deviation | 11.90 |
| Range | 53.90 |
| Trend | decreasing |
| Volatility | 4.85 |

```
 CPU Temperature (°C) over 30 time points
 Range: 40.0 to 93.9

    93.9 |         *                    
    86.2 |                              
    78.5 |                              
    70.8 |          * *                 
    63.1 |    *****  * **               
    55.4 | ***           * **           
    47.7 |*               *  ****       
    40.0 |                       *******
          +----------------------------+
           0    5    10    15    20    25   29
           Data points: 0 to 29 (n=30)

  Statistics
    Min: 40.00
    Max: 93.90
    Mean: 57.99
    Range: 53.90
    Trend: 📉 Decreasing
```

### Server Response Time (ms) over 25 samples

| Metric | Value |
|--------|-------|
| Data Points | 25 |
| Minimum | 56.80 |
| Maximum | 374.40 |
| Mean | 130.34 |
| Median | 117.90 |
| Std Deviation | 58.45 |
| Range | 317.60 |
| Trend | decreasing |
| Volatility | 33.30 |

```
 Server Response Time (ms) over 25 samples
 Range: 56.8 to 374.4

   374.4 |         *               
   329.0 |                         
   283.7 |                         
   238.3 |                         
   192.9 |                         
   147.5 |    ***** *              
   102.2 |****       ****       ***
    56.8 |               *******   
          +-----------------------+
           0   4   8   12   16   20   24
           Data points: 0 to 24 (n=25)

  Statistics
    Min: 56.80
    Max: 374.40
    Mean: 130.34
    Range: 317.60
    Trend: 📉 Decreasing
```

### Daily Active Users over 30 days

| Metric | Value |
|--------|-------|
| Data Points | 30 |
| Minimum | 993.00 |
| Maximum | 1202.00 |
| Mean | 1080.80 |
| Median | 1068.50 |
| Std Deviation | 55.68 |
| Range | 209.00 |
| Trend | increasing |
| Volatility | 28.72 |

```
 Daily Active Users over 30 days
 Range: 993.0 to 1202.0

  1202.0 |                             *
  1172.1 |                       *      
  1142.3 |                      * *   * 
  1112.4 |               ***   *   *    
  1082.6 |        **                **  
  1052.7 | *        *   *   * *         
  1022.9 |  **   *   * *     *          
   993.0 |*   ***     *                 
          +----------------------------+
           0    5    10    15    20    25   29
           Data points: 0 to 29 (n=30)

  Statistics
    Min: 993.00
    Max: 1202.00
    Mean: 1080.80
    Range: 209.00
    Trend: 📈 Increasing
```

## Methodology

- **CPU Temperature**: Synthetic data modeling a server CPU with diurnal cycles and occasional thermal spikes.
- **Response Time**: Server response times with increasing baseline load and outlier spikes.
- **Daily Active Users**: Growth trend with weekly seasonality patterns.

ASCII charts rendered at 50-character width with 8-row height.

*This report was generated from synthesized data. Agents were unable to participate due to API key limits; the build script produced this directly as a fallback.*