import sys, getopt, re, time
from os import listdir
from os.path import isfile, join, exists

OUTPUT_FILE   = 'sched.csv'
OUTPUT_HEADER = 'timestamp,cpu,usage%,schedrun,schedwait,timeslices'
OUTPUT_NL     = '\n'
DELAY_S       = 5
PRECISION     = 2
# From https://www.kernel.org/doc/Documentation/filesystems/proc.txt
SYSFS_STAT    = '/proc/stat'
SYSFS_STATS_KEYS  = {'cpuid':0, 'user':1, 'nice':2 , 'system':3, 'idle':4, 'iowait':5, 'irq':6, 'softirq':7, 'steal':8, 'guest':9, 'guest_nice':10}
SYSFS_STATS_IDLE  = ['idle', 'iowait']
SYSFS_STATS_NTID  = ['user', 'nice', 'system', 'irq', 'softirq', 'steal']
# From https://www.kernel.org/doc/Documentation/scheduler/sched-stats.txt
SYSFS_SCHEDSTAT    = '/proc/schedstat'
SYSFS_SCHEDSTAT_KEYS   = {'cpuid':0, 'yield':1,'schedule_call':3,'schedule_fail':4,'wakeup_call':5,'wakeup_local':6,'schedrun':7,'schedwait':8,'timeslices':9}
SYSFS_SCHEDSTAT_STUDY  = ['schedrun','schedwait','timeslices']
LIVE_DISPLAY = False

def print_usage():
    print('python3 sched-reader.py [--help] [--live] [--output=' + OUTPUT_FILE + '] [--delay=' + str(DELAY_S) + ' (in sec)] [--precision=' + str(PRECISION) + ' (number of decimal)]')

###########################################
# Read CPU usage
###########################################
class CpuTime(object):
    def has_time(self):
        return hasattr(self, 'idle') and hasattr(self, 'not_idle')

    def set_time(self, idle : int, not_idle : int):
        setattr(self, 'idle', idle)
        setattr(self, 'not_idle', not_idle)

    def get_time(self):
        return getattr(self, 'idle'), getattr(self, 'not_idle')

    def clear_time(self):
        if hasattr(self, 'idle'): delattr(self, 'idle')
        if hasattr(self, 'not_idle'): delattr(self, 'not_idle')

    def has_attr(self, attr_name : str):
        return hasattr(self, attr_name)

    def set_attr(self, attr_name : str, attr_val):
        return setattr(self, attr_name, attr_val)

    def get_attr(self, attr_name : str):
        return getattr(self, attr_name)

def __get_usage_of_stat_line(split : list, hist_object : CpuTime, update_history : bool = True):
    idle          = sum([ int(split[SYSFS_STATS_KEYS[idle_key]])     for idle_key     in SYSFS_STATS_IDLE])
    not_idle      = sum([ int(split[SYSFS_STATS_KEYS[not_idle_key]]) for not_idle_key in SYSFS_STATS_NTID])

    # Compute delta
    cpu_usage  = None
    if hist_object.has_time():
        prev_idle, prev_not_idle = hist_object.get_time()
        delta_idle     = idle - prev_idle
        delta_total    = (idle + not_idle) - (prev_idle + prev_not_idle)
        if delta_total>0: # Manage overflow
            cpu_usage = round(((delta_total-delta_idle)/delta_total)*100,PRECISION)
    
    if update_history: hist_object.set_time(idle=idle, not_idle=not_idle)
    return cpu_usage

def read_stat(cputime_hist : dict, update_history : bool = True):
    with open(SYSFS_STAT, 'r') as f:
        lines = f.readlines()

    measures = dict()
    lines.pop(0) # remove global line, we focus on per cpu usage
    for line in lines:
        split = line.split(' ')

        identifier = split[SYSFS_STATS_KEYS['cpuid']]
        if not identifier.startswith('cpu'): break

        if identifier not in cputime_hist: cputime_hist[identifier] = CpuTime()
        cpu_usage = __get_usage_of_stat_line(split=split, hist_object=cputime_hist[identifier], update_history=update_history)
        measures[identifier] = dict()
        measures[identifier]['usage%'] = cpu_usage

    return measures

def read_schedstat(cputime_hist : dict, update_history : bool = True, append_dict : dict = None):
    with open(SYSFS_SCHEDSTAT, 'r') as f:
        lines = f.readlines()

    schedstat_dict = append_dict
    if schedstat_dict is None:
        schedstat_dict = dict()

    for line in lines:
        split = line.split(' ')

        identifier = split[SYSFS_SCHEDSTAT_KEYS['cpuid']]
        if not identifier.startswith('cpu'): continue
        
        for metric_under_study in SYSFS_SCHEDSTAT_STUDY:
            if (identifier in cputime_hist) and (cputime_hist[identifier].has_attr(metric_under_study)):
                delta =  int(split[SYSFS_SCHEDSTAT_KEYS[metric_under_study]]) - int(cputime_hist[identifier].get_attr(metric_under_study))
                if identifier not in schedstat_dict:
                    schedstat_dict[identifier]
                schedstat_dict[identifier][metric_under_study] = delta

            if update_history:
                cputime_hist[identifier].set_attr(metric_under_study, split[SYSFS_SCHEDSTAT_KEYS[metric_under_study]])

    return schedstat_dict

def read_data(cputime_hist : dict):
    cpu_stat   = read_stat(cputime_hist=cputime_hist)
    read_schedstat(cputime_hist=cputime_hist, append_dict=cpu_stat)
    return cpu_stat

###########################################
# Main loop, read periodically
###########################################
def loop_read():
    cpu_hist = dict()
    launch_at = time.time_ns()
    while True:
        time_begin = time.time_ns()

        cpu_measures  = read_data(cputime_hist=cpu_hist)

        output(cpu_measures=cpu_measures, time_since_launch=int((time_begin-launch_at)/(10**9)))

        time_to_sleep = (DELAY_S*10**9) - (time.time_ns() - time_begin)
        if time_to_sleep>0: time.sleep(time_to_sleep/10**9)
        else: print('Warning: overlap iteration', -(time_to_sleep/10**9), 's')

def output(cpu_measures : dict, time_since_launch : int):

    if LIVE_DISPLAY and cpu_measures:
        for cpuid, value in cpu_measures.items():
            print(cpuid, value)
        print('---')

    # Dump reading
    with open(OUTPUT_FILE, 'a') as f:
        for cpuid, measure in cpu_measures.items():
            if measure['usage%'] is not None:
                f.write(str(time_since_launch) + ',' + cpuid + ',' + str(measure['usage%']) + ',' +  ','.join([str(measure[key]) for key in ['schedrun','schedwait','timeslices']]) + OUTPUT_NL)

###########################################
# Entrypoint, manage arguments
###########################################
if __name__ == '__main__':

    short_options = 'hlo:p:d:'
    long_options = ['help', 'live', 'output=', 'precision=', 'delay=']

    try:
        arguments, values = getopt.getopt(sys.argv[1:], short_options, long_options)
    except getopt.error as err:
        print(str(err))
        print_usage()
    for current_argument, current_value in arguments:
        if current_argument in ('-h', '--help'):
            print_usage()
            sys.exit(0)
        elif current_argument in('-l', '--live'):
            LIVE_DISPLAY= True
        elif current_argument in('-o', '--output'):
            OUTPUT_FILE= current_value
        elif current_argument in('-p', '--precision'):
            PRECISION= int(current_value)
        elif current_argument in('-d', '--delay'):
            DELAY_S= float(current_value)

    try:
        # Init output
        with open(OUTPUT_FILE, 'w') as f: f.write(OUTPUT_HEADER + OUTPUT_NL)
        # Launch
        loop_read()
    except KeyboardInterrupt:
        print('Program interrupted')
        sys.exit(0)