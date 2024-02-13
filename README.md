# Simple linux Sched stats reader

Easily measure the scheduler performances

## Features

Monitor the per-core usage associated to their individual scheduling statistics
Measures are formatted on a ready to use CSV (under normalised timestamp keys)\
Live display is also possible with ```--live``` option\

## Usage

```bash
python3 sched-reader.py --help
```

To dump on default ```sched.csv``` while also displaying measures to the console
```bash
python3 sched-reader.py --live
```

To change default values:
```bash
python3 sched-reader.py --delay=(sec) --precision=(number of digits) --output=sched.csv
```
