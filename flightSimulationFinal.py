##### import relevant libraries #####
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import random
from random import randrange, uniform
import simpy
###
import dash
import dash_html_components as html
import dash_table
from dash import Dash
import dash_core_components as dcc
###


# to display all columns when printing
pd.set_option('display.max_columns', None)
pd.set_option('expand_frame_repr', False)
# Don't forget to seed remove at end
# random.seed(123456)
##########

####### Global Variables #######
timekeeper = 0
currentDateTime = datetime(2019, 6, 18, 18, 0, 0)
timeList=[]
location=""
database=[]
counter=-1
arrivalDepart=1

##### create classes and functions #####
# get flights for current date
def getFlightsForDay(inDate):
    dayFlights = flight_sch[(flight_sch['Sch Arv Date'] == inDate) | (flight_sch['Sch Dept Date'] == inDate)]
    dayFlights.reset_index(inplace=True)
    return dayFlights

# creates the Departure and Arrival Boards
def convertToDf(objectList, objectList2, flag,gateReassign):
    if flag == 0:
        newGate=""
        print(getCurrentDateTime())
        if len(gateReassign)>0:
            newGate=gateReassign
        timeList.append(getCurrentDateTime())
        df = []
        for i in objectList:
            row = i.updateArrivalReport(i.arrivalInformation,newGate)
            if len(row) > 0:
                df.append(row)
        dateTimeTitle=str(getCurrentDateTime())
        

        df = pd.DataFrame(df, columns=['Tail Number', 'Coming From', 'Arriving', 'Gate','Report'], index=None)
        df['Time']= np.nan
        df.Time.iloc[0] = dateTimeTitle
        return orderByTime(df, flag)
    else:
        print(getCurrentDateTime())
        timeList.append(getCurrentDateTime())
        newGate=""
        df = []
        if len(gateReassign)>0:
            newGate=gateReassign
        for i in (objectList2):
            row = i.updateDepartureReport(i.departInformation,newGate)
            if len(row) > 0:
                df.append(row)
        dateTimeTitle=str(getCurrentDateTime())
        df = pd.DataFrame(df, columns=['Tail Number', 'Going To', 'Departing', 'Gate', 'Report'], index=None)
        df['Time']= np.nan
        df.Time.iloc[0] = dateTimeTitle
        return orderByTime(df, flag)


# orders the arrival and departure board by time
def orderByTime(df, flag):
    
    if flag == 0:
        df = df.sort_values(by='Arriving', ascending=True)
        return df
    else:
        df = df.sort_values(by='Departing', ascending=True)
    
    return df


# get current DateTime
def getCurrentDateTime():
    global timekeeper
    global currentDateTime
    if timekeeper >= 60:
        quotient = timekeeper // 60
        remainder = timekeeper % 60
        combined = currentDateTime + timedelta(hours=quotient)
        combined = combined + timedelta(minutes=remainder)
    else:
        combined = currentDateTime + timedelta(minutes=timekeeper)
    return combined


############## Gate Functions ##################
# create gate availability dataframe for 24 hour period by minute
def initialise_gate_avail_df(flt_dt):
    flt_dt = datetime.combine(datetime.strptime(flt_dt, '%Y-%m-%d').date(), datetime.min.time())
    datetime_list = [flt_dt + timedelta(minutes=x) for x in range(0, 1440)]
    time_list = [x.time() for x in datetime_list]
    gate_availability = pd.DataFrame()
    gate_availability['Time'] = time_list
    # initialise availability for all times to True (available)
    gate_availability['Available'] = True
    gate_availability.set_index('Time', inplace=True)
    return gate_availability


# create gate availability from flight schedule
def update_gate_avail_with_flt_sch(flt_dt, flightObjects, gateObjects):
    flt_dt = datetime.strptime(flt_dt, '%Y-%m-%d').date()
    status = False
    for flt in flightObjects:
        # select the gate for the flight
        current_gate = flt.gate
        # calculate time range from flight schedule
        # if flight arrived yesterday make unavailable for an hour before today's flight
        if flt.arrivalDate < flt_dt:
            t2 = flt.departTime
            t2 = datetime.combine(datetime.today(), t2)
            t1 = (t2 - timedelta(hours=1))

        # if flight arrives today and leaves tomorrow make unavailable for an hour after landing today
        elif flt.departDate > flt_dt:
            t1 = flt.arrivalTime
            t1 = datetime.combine(datetime.today(), t1)
            # if flight leaves within an hour of midnight make unavailable until midnight
            if t1 > datetime(datetime.today().year, datetime.today().month, datetime.today().day, 22, 59, 0):
                t2 = datetime(datetime.today().year, datetime.today().month, datetime.today().day, 23, 59, 0)
            else:
                t2 = (t1 + timedelta(hours=1))
        else:
            t1 = datetime.combine(datetime.today(), flt.arrivalTime)
            t2 = datetime.combine(datetime.today(), flt.departTime)
        # change t1 and t2 from datetime to time
        t1 = t1.time()
        t2 = t2.time()
        # update the gate availability
        gateObjects[current_gate].update_gate_availability(t1, t2, status)


# create function to find closest gate - closest numerically or lowest in new concourse
def choose_closest_gate(old_gate, new_gate_list, flag):
    gate_dist = 100
    closest_gate = ''
    gate_num_old = int(old_gate[1:])
    # if there's available gates on the same concourse choose closest numerically
    if flag == 1:
        for gate in new_gate_list:
            gate_num_new = int(gate[1:])
            dist = abs(gate_num_old - gate_num_new)
            if dist < gate_dist:
                gate_dist = dist
                closest_gate = gate
    # if all fo the gates are on different concourses choose the lowest gate number
    elif flag == 0:
        new_gate_list.sort(key=lambda x: x[1:])
        for gate in new_gate_list:
            gate_num_new = int(gate[1:])
            if gate_num_new < gate_dist:
                gate_dist = gate_num_new
                closest_gate = gate
    # print(old_gate,closest_gate)
    return closest_gate


# in case of no available gates, find next gate available
def next_avail_gate(gateObjects, gate_list, arrv_dt_tm, dep_dt_tm):
    diff = int((dep_dt_tm - arrv_dt_tm).total_seconds() / 60.0) + 1
    new_gate = ''
    new_start_time = arrv_dt_tm
    new_end_time = dep_dt_tm
    time_list = [(arrv_dt_tm + timedelta(hours=i / 60)) for i in range(diff)]
    # from start time to midnight
    for gate in gate_list:
        for t in time_list:
            if gateObjects[gate].gate_availability.at[t.time(), 'Available'] == True:
                if gateObjects[gate].check_gate_availability(t.time(), (t + timedelta(hours=diff/60)).time()) == True:
                    new_time = t
                    break
        if new_time < new_start_time:
            new_start_time = new_time
            new_end_time = new_time + timedelta(hours=diff/60)
            new_gate = gate
    return new_gate, new_start_time, new_end_time


# reassign gate and update gate availability after flight delay
def check_then_update_avail(delayed_flt, gateObjects, flt_dt):
    # update original gate availablilty to available at old time
    current_gate = delayed_flt.gate
    gateObjects[current_gate].update_gate_availability(delayed_flt.arrivalTime, delayed_flt.departTime, True)
    # find new flight times
    delayed_flt.update_arrv_dept_tm(flt_dt)
    # check if the gate is still available
    curr_avail = gateObjects[current_gate].check_gate_availability(delayed_flt.arrivalTime, delayed_flt.departTime)
    # if yes do update gate availability
    if curr_avail == True:
        gateObjects[delayed_flt.gate].update_gate_availability(delayed_flt.arrivalTime, delayed_flt.departTime, False)
    # otherwise find which gates are available and then pick the closest one
    elif curr_avail == False:
        gate_list_temp = np.delete(gate_list, np.where(gate_list == current_gate))
        avail_gates_same = []
        avail_gates_diff = []
        # prioritise gates in same concourse
        concourse = current_gate[:1]
        same_concourse = [i for i in gate_list_temp if i.startswith(concourse)]
        if len(same_concourse) > 0:
            for gate in same_concourse:
                gate_avail = gateObjects[gate].check_gate_availability(delayed_flt.arrivalTime, delayed_flt.departTime)
                if gate_avail == True:
                    avail_gates_same.append(gate)
        elif len(same_concourse) == 0:
            for gate in gate_list_temp:
                gate_avail = gateObjects[gate].check_gate_availability(delayed_flt.arrivalTime, delayed_flt.departTime)
                if gate_avail == True:
                    avail_gates_diff.append(gate)
        # if there's gates available at the new time
        if len(avail_gates_same) > 0:
            # choose closest and reassign gate
            delayed_flt.gate = choose_closest_gate(current_gate, avail_gates_same, 1)
            # update gate availablility
            gateObjects[delayed_flt.gate].update_gate_availability(delayed_flt.arrivalTime, delayed_flt.departTime, False)
        elif len(avail_gates_diff) > 0:
            # choose closest and reassign gate
            delayed_flt.gate = choose_closest_gate(current_gate, avail_gates_diff, 0)
            # update gate availablility
            gateObjects[delayed_flt.gate].update_gate_availability(delayed_flt.arrivalTime, delayed_flt.departTime, False)
        # if there's no gates available at the new time
        elif len(avail_gates_same) == 0 and len(avail_gates_diff) == 0:
            new_gate, new_arrv_tm, new_dep_tm = next_avail_gate(gateObjects, gate_list, delayed_flt.arrivalDateTime, delayed_flt.departDateTime)
            delayed_flt.gate = new_gate
            delayed_flt.departTime = new_arrv_tm.time()
            delayed_flt.arrivalTime = new_dep_tm.time()
            delayed_flt.arrivalDateTime = new_arrv_tm
            delayed_flt.departDateTime = new_dep_tm
        # update gate availablility
        gateObjects[delayed_flt.gate].update_gate_availability(delayed_flt.arrivalTime, delayed_flt.departTime, False)


################## Gate Class ##################
# define gate class
class Gate:
    def __init__(self, name, gate_availability):
        self.name = name
        self.gate_availability = gate_availability

    def update_gate_availability(self, t1, t2, status):
        # convert t1 and t2 from time to datetime
        t1 = datetime.combine(datetime.today(), t1)
        t2 = datetime.combine(datetime.today(), t2)
        # create list of times starting from t1 to t2
        time_list = [(t1 + timedelta(hours=i / 60)).time() for i in range(int((t2 - t1).total_seconds() / 60.0) + 1)]
        # update availability to status for each time from t1 to t2
        for t in time_list:
            self.gate_availability.at[t, 'Available'] = status

    def check_gate_availability(self, t1, t2):
        # convert t1 and t2 from time to datetime
        t1 = datetime.combine(datetime.today(), t1)
        t2 = datetime.combine(datetime.today(), t2)
        # create list of times starting from t1 to t2
        time_list = [(t1 + timedelta(hours=i / 60)).time() for i in range(int((t2 - t1).total_seconds() / 60.0) + 1)]
        avail_list = []
        # append availability for each time from t1 to t2
        for t in time_list:
            avail_list.append(self.gate_availability.at[t, 'Available'])
        # if any one time is False (not available) then availability = False
        if False in avail_list:
            return False
        else:
            return True


################## Flight Class ##################
# define flight class (pseudo flights, for gate testing purposes)
class Flight:
    def __init__(self, flightNumber, fromDestination, arrivalDateTime, departDateTime, gate):
        # initialisers
        self.id = flightNumber
        self.od = fromDestination
        self.gate = gate
        self.delayLen = 0
        self.report = "TBD"
        self.arrivalDateTime = arrivalDateTime.to_pydatetime()
        self.departDateTime = departDateTime.to_pydatetime()
        self.arrivalDate = arrivalDateTime.date()
        self.departDate = departDateTime.date()
        self.arrivalTime = arrivalDateTime.time()
        self.departTime = departDateTime.time()
        cd = getCurrentDateTime()
        self.arrivalInformation = []
        self.departInformation = []
        if self.arrivalDateTime >= datetime(cd.year, cd.month, cd.day, 0, 0, 0):
            self.arrivalInformation = self.createArrivalBoard(5)
        if self.departDateTime <= datetime(cd.year, cd.month, cd.day, 23, 59, 0):
            self.departInformation = self.createDepartureBoard(5)
        
    # return gate
    def getGate(self):
        return self.gate

    # checks the status of the flight and returns a delay and delay length if appropriate
    def checkStatus(self, flag):
        # Random selection to indicate when a flight is delayed
        rand1 = uniform(0, 1)
        # Random selection to indicate how long a flight is delayed
        rand2 = uniform(0, 1)
        
        if flag == -1:
            if self.report == 'ONTIME' and rand1 < 0.0006:
                self.report == 'DELAYED'
                # set the initial delay length
                if rand2 <= 0.5:
                    self.report = 'DELAYED'
                    self.delayLen = random.randint(1, 60)
                elif rand2 > 0.5 and rand2 <= 0.8:
                    self.report = 'DELAYED'
                    self.delayLen = random.randint(61, 120)
                elif rand2 > 0.8:
                    self.report = 'DELAYED'
                    self.delayLen = random.randint(121, 480)
            # update delay length
            elif self.report == 'DELAYED' and rand2 > 0.95 and rand2 <= 0.99:
                self.report = 'DELAYED'
                self.delayLen += random.randint(1, 60)
            elif self.report == 'DELAYED' and rand2 > 0.99:
                self.report = 'DELAYED'
                self.delayLen += random.randint(61, 120)
    def prettyPrintDelay(self,flag):
        # if delayed, pretty print delay length
        ret = ""
        if flag == 0 or flag == 1:
            if self.report == 'DELAYED':
                if self.delayLen < 60:
                    if flag == 0:
                        eta = self.arrivalDateTime + timedelta(minutes=self.delayLen)
                        ret = self.report + " " + str(self.delayLen) + " " + 'mins (ETA: ' + str(eta.time()) + ")"
                    elif flag == 1:
                        etd = self.departDateTime + timedelta(minutes=self.delayLen)
                        ret = self.report + " " + str(self.delayLen) + " " + 'mins (ETD: ' + str(etd.time()) + ")"
                elif self.delayLen >= 60:
                    quotient = self.delayLen // 60
                    remainder = self.delayLen % 60
                    if flag == 0:
                        eta = self.arrivalDateTime + timedelta(minutes=self.delayLen)
                        if remainder == 0:
                            ret = self.report + " " + str(quotient) + " " + 'hr (ETA: ' + str(eta.time()) + ")"
                        else:
                            ret = self.report + " " + str(quotient) + " " + 'hr '+ str(remainder)+' mins (ETA: ' + str(eta.time()) + ")"
                    elif flag == 1:
                        etd = self.departDateTime + timedelta(hours=quotient)
                        if remainder == 0:
                            ret = self.report + " " + str(quotient) + " " + 'hr (ETD: ' + str(etd.time()) + ")"
                        else:
                            ret = self.report + " " + str(quotient) + " " + 'hr '+ str(remainder)+' mins (ETD: ' + str(etd.time()) + ")"
        return self.report, ret

    def update_arrv_dept_tm(self, flt_dt):
    # if flight arrives yesterday and leaves today only update dept time
        if self.arrivalDate < flt_dt:
            self.departTime = (datetime.combine(datetime.today(), self.departTime) + timedelta(minutes=self.delayLen)).time()
            self.departDateTime = self.departDateTime + timedelta(minutes=self.delayLen)
        # if flight arrives today and leaves tomorrow
        elif self.departDate > flt_dt:
            t_curr = self.arrivalDateTime
            today = getCurrentDateTime()
            tomorrow = getCurrentDateTime() + timedelta(days=1)
            t_midnight = datetime(today.year, today.month, today.day, 23, 59, 0)
            t_midnight_1 = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
            t_new = self.arrivalDateTime + timedelta(minutes=self.delayLen)
            # if new departure time is after midnight then ignore it - the flight is cancelled
            if t_curr <= t_midnight and t_new >= t_midnight_1:
                pass
            # otherwise just change the arrival time
            else:
                self.arrivalTime = (datetime.combine(datetime.today(), self.arrivalTime) + timedelta(minutes=self.delayLen)).time()
                self.arrivalDateTime = self.arrivalDateTime + timedelta(minutes=self.delayLen)
        else:
            t_curr_arrv = self.arrivalDateTime
            t_curr_dep = self.departDateTime
            today = getCurrentDateTime()
            tomorrow = getCurrentDateTime() + timedelta(days=1)
            t_midnight = datetime(today.year, today.month, today.day, 23, 59, 0)
            t_midnight_1 = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
            t_new_arrv = self.arrivalDateTime + timedelta(minutes=self.delayLen)
            t_new_dep = self.departDateTime + timedelta(minutes=self.delayLen)
            # if new arrival or departure time is after midnight then ignore it - the flight is cancelled
            if (t_curr_arrv <= t_midnight and t_new_arrv >= t_midnight_1) or (t_curr_dep <= t_midnight and t_new_dep >= t_midnight_1):
                pass
            # otherwise just update the arrival/depature time
            else:
                self.arrivalTime = (datetime.combine(datetime.today(), self.arrivalTime) + timedelta(minutes=self.delayLen)).time()
                self.departTime = (datetime.combine(datetime.today(), self.departTime) + timedelta(minutes=self.delayLen)).time()
                self.arrivalDateTime = self.arrivalDateTime + timedelta(minutes=self.delayLen)
                self.departDateTime = self.departDateTime + timedelta(minutes=self.delayLen)

    # called at the beginning to initialze the arrival board
    def createArrivalBoard(self, timeBound):
        # initializes the arrival board
        cd = getCurrentDateTime()
        ret = []
        if self.arrivalDateTime < cd:
            self.report = 'ARRIVED'
        elif self.arrivalDateTime > cd:
            self.report = 'ONTIME'
        elif self.arrivalDateTime == cd:
            self.report = 'LANDING'
        ret.append(self.id)
        ret.append(self.od)
        ret.append(self.arrivalDateTime)
        ret.append(self.gate)
        ret.append(self.report)
        return ret

    # called at the beginning to initialze the departure board
    def createDepartureBoard(self, timeBound):
        # initializes departBoard
        cd = getCurrentDateTime()
        ret = []
        if self.departDateTime > cd:
            self.report = 'ONTIME'
        elif self.departDateTime < cd:
            self.report = "DEPARTED"
        elif (self.departDateTime == cd):
            self.report = 'DEPARTING'
        ret.append(self.id)
        ret.append(self.od)
        ret.append(self.departDateTime)
        ret.append(self.gate)
        ret.append(self.report)
        # print(self.report)
        return ret

    # function to update the departure board
    def updateDepartureReport(self, departInformation,new_gate):
        temp, toPrint = self.prettyPrintDelay(1)
        global departObjects
        cd = getCurrentDateTime()

        midnight = datetime(self.departDate.year, self.departDate.month, self.departDate.day, 23, 59, 0)
        if len(new_gate)>0:
            if departInformation[0]==new_gate[2]  and departInformation[1]==new_gate[3]:
                departInformation[3]="REASSIGNED "+new_gate[1]
        if self.report != "DELAYED" and self.report != 'CANCELLED':
            if self.departDateTime > datetime(cd.year, cd.month, cd.day, 23, 59, 59):
                departInformation = []
            if self.departDateTime + timedelta(hours=2) < cd and departInformation[2] != cd:
                departInformation = []
                updateObjectList(1, 0)
            elif self.departDateTime > cd:
                departInformation[-1] = 'ONTIME'
                self.report = 'ONTIME'
            elif self.departDateTime + timedelta(hours=2) >= cd and self.departDateTime != cd:
                departInformation[-1] = "DEPARTED"
                self.report = 'DEPARTED'
            elif (self.departDateTime == cd):
                departInformation[-1] = 'DEPARTING'
                self.report = 'DEPARTING'
        elif self.report == "CANCELLED":
            departInformation[-1] = 'CANCELLED'
            self.report = 'CANCELLED'
        else:
            departInformation[-1] = toPrint
        # if delayed
        if len(departInformation) != 0 and self.report == "DELAYED":

            if cd == self.departDateTime + timedelta(minutes=self.delayLen):
                departInformation[-1] = "DEPARTING"
                self.departDateTime = cd
                self.report = "DEPARTING"
            elif self.departDateTime + timedelta(minutes=self.delayLen) >= midnight:
                departInformation[-1] = "CANCELLED"
                self.report = "CANCELLED"
        return departInformation

    # Function to update the arrival board
    def updateArrivalReport(self, arrivalInformation,new_gate):
        temp, toPrint = self.prettyPrintDelay(0)
        cd = getCurrentDateTime()
        global arrivalObjects
        midnight = datetime(self.arrivalDate.year, self.arrivalDate.month, self.arrivalDate.day, 23, 59, 0)
        
        if len(new_gate)>0:
            if arrivalInformation[0]==new_gate[2]  and arrivalInformation[1]==new_gate[3]:
                arrivalInformation[3]="REASSIGNED "+new_gate[1]
                
        
        if self.report != "DELAYED" and self.report != 'CANCELLED':
            if self.arrivalDateTime + timedelta(hours=2) < cd:
                arrivalInformation = []
                updateObjectList(0, 0)
            elif self.arrivalDateTime > cd:
                arrivalInformation[-1] = 'ONTIME'
                self.report = "ONTIME"
            elif self.arrivalDateTime + timedelta(minutes=15) >= cd and (self.arrivalDateTime != cd):
                arrivalInformation[-1] = "ARRIVED"
                self.report = "ARRIVED"
            elif self.arrivalDateTime + timedelta(minutes=15) < cd and self.arrivalDateTime + timedelta(
                    hours=2) >= cd and (self.arrivalDateTime != cd):
                arrivalInformation[-1] = "BAGS DELIVERED"
                self.report = "BAGS DELIVERED"
            elif (self.arrivalDateTime == cd):
                arrivalInformation[-1] = 'LANDING'
                self.report = "LANDING"
        elif self.report == 'CANCELLED':
            arrivalInformation[-1] = 'CANCELLED'
            self.report = 'CANCELLED'
            # del arrivalObjects[idx]
        else:
            arrivalInformation[-1] = toPrint
        # if flight is delayed
        if len(arrivalInformation) != 0 and self.report=='DELAYED':
            print("delayed",self.delayLen,self.id)
            arrivalInformation[-1] = toPrint
            if cd == self.arrivalDateTime + timedelta(minutes=self.delayLen):
                arrivalInformation[-1] = "LANDING"
                self.arrivalDateTime = cd
                self.report = "LANDING"
            elif self.arrivalDateTime + timedelta(minutes=self.delayLen) > midnight:
                
                arrivalInformation[-1] = "CANCELLED"
                self.report = "CANCELLED"
        return arrivalInformation


def updateObjectList(flag, delayLen):
    cd = getCurrentDateTime()
    global departObjects
    global arrivalObjects
    if flag == 0:
        arrivalObjects = [x for x in arrivalObjects if
                          not (x.arrivalDateTime + timedelta(hours=2) < cd and x.arrivalDateTime != cd)]
    else:
        departObjects = [x for x in departObjects if
                         not ((x.departDateTime + timedelta(hours=2) < cd and x.departDateTime != cd) or
                              x.departDateTime + timedelta(minutes=delayLen) > datetime(cd.year, cd.month, cd.day, 23,
                                                                                        59, 59))]



# create overall update function that will be called each run of the simulation
# Prints the boards
def update(env, arrivalObjects, departOjects, flightObjects, gateObjects, inDate):

    text_file = open("index.html", "w") 
    while True:
        print('-----------------')
        global timekeeper

        timekeeper = env.now
        gateReassign=[]
        
        for flt in flightObjects:
            if flt.arrivalDateTime < getCurrentDateTime() + timedelta(hours=6):
                original_delay = flt.delayLen
                original_status = flt.report
                original_gate = flt.gate
                flt.checkStatus(-1)
                if original_delay != flt.delayLen:
                    check_then_update_avail(flt, gateObjects, datetime.strptime(inDate, '%Y-%m-%d').date())
                if (original_gate!=flt.gate):
                    
                    gateReassign=[original_gate,flt.gate,flt.id,flt.od]
                    print(gateReassign)
                   
        db = convertToDf(arrivalObjects, departObjects, arrivalDepart,gateReassign)
        # print(db)
        database.append(db)

        yield env.timeout(1)


if __name__ == '__main__':
    ##### initialise data #####
    # import data
    filename='bos_flights.csv'
    flight_sch = pd.read_csv(filename)
    if 'ric' in filename:
        location="Richmond"
    elif 'bos' in filename:
        location="Boston"
    else:
        location="Chicago"

    # select flight date
    inDate = '2019-06-18'

    # select schedule for inDate
    flight_sch = getFlightsForDay(inDate)
    flight_sch.sort_values('Scheduled Arvl Datetime', inplace=True)
    # print(flight_sch)
    # format df and column datatypes
    flight_sch['Sch Arv Date'] = flight_sch['Sch Arv Date'].astype('datetime64[ns]')
    flight_sch['Sch Arv Date'] = flight_sch['Sch Arv Date'].dt.date
    flight_sch['Sch Dept Date'] = flight_sch['Sch Dept Date'].astype('datetime64[ns]')
    flight_sch['Sch Dept Date'] = flight_sch['Sch Dept Date'].dt.date
    flight_sch['Sch Arv Time'] = pd.to_datetime(flight_sch['Sch Arv Time'], format='%H:%M:%S').dt.time
    flight_sch['Sch Dept Time'] = pd.to_datetime(flight_sch['Sch Dept Time'], format='%H:%M:%S').dt.time
    # flight_sch['Scheduled Arvl Datetime'].astype('datetime64[ns]')
    # flight_sch['Scheduled Dept Datetime'].astype('datetime64[ns]')
    flight_sch['Scheduled Dept Datetime'] = pd.to_datetime(
        flight_sch['Sch Dept Date'].astype(str) + " " + flight_sch['Sch Dept Time'].astype(str))
    flight_sch['Scheduled Arvl Datetime'] = pd.to_datetime(
        flight_sch['Sch Arv Date'].astype(str) + " " + flight_sch['Sch Arv Time'].astype(str))

    # create gate_availability dataframe
    gate_availability = initialise_gate_avail_df(inDate)

    # create all gate class objects
    gate_list = flight_sch['Gate'].unique()
    gateObjects = {name: Gate(name, gate_availability.copy(deep=True)) for name in gate_list}

    # create flight class objects (pseudo code, for gate testing purposes)
    flightObjects = [
        Flight(a['Tail Number'], a['Upline station'], a['Scheduled Arvl Datetime'], a['Scheduled Dept Datetime'],
               a['Gate'])
        for b, a in flight_sch.iterrows()]

    # update gate availability from the flight schedule
    update_gate_avail_with_flt_sch(inDate, flightObjects, gateObjects)

    # create arrival, dep board list
    arrivalBoard = []
    departBoard = []

    arrivalObjects = []
    departObjects = []
    # flightObjects=[i for i in flightObjects if i.arrivalDateTime>=datetime(cd.year, cd.month, cd.day, 0,0, 0)]
    for i in flightObjects:
        if len(i.arrivalInformation) > 0:
            arrivalObjects.append(i)
    for i in flightObjects:
        if len(i.departInformation) > 0:
            departObjects.append(i)
            
   
    ##### set up and running simulated environment #####
    env = simpy.rt.RealtimeEnvironment(factor=.25)
    env.process(update(env, arrivalObjects, departObjects, flightObjects, gateObjects, inDate))
    env.run(until=1441)
    ####################################################
    app = dash.Dash(__name__)
    def outputArrival():
        def getData():
            global counter
            global database

            if counter<len(database):
                print(counter)
                counter+=1
                return database[counter].to_dict('records')
        
        tblcols=[{'name': 'Tail Number', 'id': 'Tail Number'},
                 {'name': 'Coming From', 'id': 'Coming From'},
                 {'name': 'Arriving', 'id': 'Arriving'},
                 {'name': 'Gate', 'id': 'Gate'},
                 {'name': 'Report', 'id': 'Report'},
                 {'name': 'Time', 'id': 'Time'}]

        heading = "Welcome to {place}!".format(place=location)
        app.layout = html.Div([          
              html.H3(heading,style={'color': 'black', 'font-family':'Lucida Handwriting','fontSize': 28,
                'font-weight': 'bold','textAlign': 'center','padding-top':'0px','margin-top':'0px'}),
              dcc.Interval('graph-update', interval = 1500, n_intervals = 0),
              dash_table.DataTable(
                  id = 'table',
                  data = getData(),
                  columns=tblcols,
                style_header={'fontSize':16,'font-family':'Lucida Console','backgroundColor':"gainsboro", 'border': '1px solid black',
                'whiteSpace': 'normal','height': 'auto'},
                style_data=dict(backgroundColor="aliceblue"),
                style_cell={'fontSize':14, 'font-family':'Lucida Console', 'border': '0px solid black'},
                style_cell_conditional=[
                    {'if': {'column_id': 'Tail Number'},
                     'width': '{}%'.format(len('Tail Number'))},
                    {'if': {'column_id': 'Coming From'},
                     'width': '{}%'.format(len('Coming From'))},
                     {'if': {'column_id': 'Gate'},
                     'width': '{}%'.format(len('Gate'))},
                    {'if': {'column_id': 'Arriving'},
                     'width': '15%'},
                     {'if': {'column_id': 'Time'},
                     'width': '15%',
                     'border': '0px solid black',
                     'backgroundColor':'white'}
                ],
                style_data_conditional=
                [
                    {
                        'if': {
                            'filter_query': '{Time} is blank',
                            'column_id': 'Time'
                        },
                        'backgroundColor': 'white',
                        'border': '0px solid white',
                        'color': 'white'
                    } 
                ]
                 
                )],style={'background-image': 'url(https://www.metoffice.gov.uk/binaries/content/gallery/metofficegovuk/hero-images/weather/cloud/altocumulus.jpg)'})
       
        @app.callback(
                dash.dependencies.Output('table','data'),
                [dash.dependencies.Input('graph-update', 'n_intervals')])
        def updateTable(n):
             return getData()

    def outputDeparture():
        def getData():
            global counter
            global database

            if counter<len(database):
                print(counter)
                counter+=1
                return database[counter].to_dict('records')
        
        tblcols=[{'name': 'Tail Number', 'id': 'Tail Number'},
                 {'name': 'Going To', 'id': 'Going To'},
                 {'name': 'Departing', 'id': 'Departing'},
                 {'name': 'Gate', 'id': 'Gate'},
                 {'name': 'Report', 'id': 'Report'},
                 {'name': 'Time', 'id': 'Time'}]

        heading = "Thanks For Visiting {place}!".format(place=location)
        app.layout = html.Div([          
              html.H3(heading,style={'color': 'black', 'font-family':'Lucida Handwriting','fontSize': 28,
                'font-weight': 'bold','textAlign': 'center','padding-top':'0px','margin-top':'0px'}),
              dcc.Interval('graph-update', interval = 1500, n_intervals = 0),
              dash_table.DataTable(
                  id = 'table',
                  data = getData(),
                  columns=tblcols,
                style_header={'fontSize':16,'font-family':'Lucida Console','backgroundColor':"gainsboro", 'border': '1px solid black',
                'whiteSpace': 'normal','height': 'auto'},
                style_data=dict(backgroundColor="aliceblue"),
                style_cell={'fontSize':14, 'font-family':'Lucida Console', 'border': '0px solid black'},
                style_cell_conditional=[
                    {'if': {'column_id': 'Tail Number'},
                     'width': '{}%'.format(len('Tail Number'))},
                    {'if': {'column_id': 'Going To'},
                     'width': '{}%'.format(len('Going To'))},
                     {'if': {'column_id': 'Gate'},
                     'width': '{}%'.format(len('Gate'))},
                    {'if': {'column_id': 'Departing'},
                     'width': '15%'},
                    {'if': {'column_id': 'Time'},
                     'width': '15%',
                     'border': '0px solid black',
                     'backgroundColor':'white'}
                ],
                style_data_conditional=
                [
                    {
                        'if': {
                            'filter_query': '{Time} is blank',
                            'column_id': 'Time'
                        },
                        'backgroundColor': 'white',
                        'border': '0px solid white',
                        'color': 'white'
                    } 
                ]
                 
                )],style={'background-image': 'url(https://www.metoffice.gov.uk/binaries/content/gallery/metofficegovuk/hero-images/weather/cloud/altocumulus.jpg)'})
       
        @app.callback(
                dash.dependencies.Output('table','data'),
                [dash.dependencies.Input('graph-update', 'n_intervals')])
        def updateTable(n):
             return getData()
    
    if arrivalDepart==0:
        outputArrival()        
        app.run_server(debug=True, port=10451)
    elif arrivalDepart==1:
        outputDeparture()        
        app.run_server(debug=True, port=10451)
