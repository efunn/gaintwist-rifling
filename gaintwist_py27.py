import numpy as np

def gaintwist(ti, tf, L, Z):
    m0 = 360/ti
    m1 = 360/tf
    a = (m1-m0)/(2*L)
    b = m0
    Y = a*Z*Z + b*Z
    return Y

def coolcycle(f):
    f.write('M7\nG4 P3\nM9\n') # Coolant Cycle for Drill Rifler

def groove(f, Z, Y, RATE, incrgroove, grooveidx, revgroovebool):
    if not(revgroovebool):
        groove_type='(FORWARD CUT '
    else:
        groove_type='(REVERSE '
    slowdowndistance = 1
    feedratereduce = .6
    endfeedrate = RATE*feedratereduce
    f.write(groove_type+'GROOVE '+repr(grooveidx+1)+')\n')
    f.write('G1 F'+repr(RATE)+' ')
    for idx in range(Z.size): 
        f.write('A'+'%.3f'%(Y[idx]+incrgroove*grooveidx)+' Z'+'%.3f'%Z[idx]+'\n')
        if (abs(Z[idx]-Z[Z.size-1]) > slowdowndistance):
            f.write('         ')
        if ((idx != (Z.size-1)) and (revgroovebool == 1)) and ((Z[idx]-Z[Z.size-1]) <= slowdowndistance):
            f.write('   F'+repr(int(RATE-RATE*feedratereduce*(1-((Z[idx+1]-Z[Z.size-1])/slowdowndistance))))+' ')
        if ((idx != (Z.size-1)) and (revgroovebool == 0)) and ((-Z[idx]+Z[Z.size-1]) <= slowdowndistance):
            f.write('   F'+repr(int(RATE-RATE*feedratereduce*(1-((-Z[idx+1]+Z[Z.size-1])/slowdowndistance))))+' ')

def turn(f, RATE, incrgroove, grooveidx):
    f.write('G1 F'+repr(RATE)+' A'+repr(incrgroove*grooveidx)+'\n')

def advancecutter(f, TURNRATE, SLOWTURNRATE, LINEARRATE, advancedegrees, Z):
    f.write('G1 F'+repr(TURNRATE)+' A'+repr(round(advancedegrees,3))+' (adjust A__ for cutter height)\n')
    f.write('G1 F'+repr(LINEARRATE)+' Z'+repr(round(-0.5,3))+'\n')
    f.write('G1 F'+repr(SLOWTURNRATE)+' A0\n')
    f.write('G1 F'+repr(LINEARRATE)+' Z'+repr(round(0,3))+'\n')


def gcodegen(filename, Z, Y, numgrooves, rate, turnrate, advancedegrees, comments):
    # set up parameters
    RATE = rate
    TURNRATE = turnrate
    SLOWTURNRATE = 1500
    LINEARRATE = 6
    Zfwd = Z
    Zrev = Z[::-1] 
    Yfwd = Y
    Yrev = Y[::-1]
    incrgroove = 360/numgrooves

    # open gcode file and write
    gc = open(filename+'.nc','w')
    gc.write('(filename: '+filename+')\n')
    gc.write('(comments: '+comments+')\n')
    # Main Program Start
    gc.write('G17 G20 G40 G49 G64 G80 G90\n')
    gc.write('M98 P2000 L5 (adjust L__ for N-1 cycles)\n') #Subroutine L value is number of cycles
    gc.write('M98 P2001 L1\n') 
    gc.write('M30\n') #Main Program Stop
    gc.write('\n')

    # O1000: main groove subroutine (does N grooves forward, N-1 grooves backwards)
    # O1005: final groove return subroutine (does Nth groove backwards)
    # O2000: main groove + final groove subroutine (no stop)
    # O2001: main groove + final groove subroutine (M0 stop before final groove return)

    #########################################
    # advance cutter subroutine start point #
    #########################################
    gc.write('O0500\n')
    advancecutter(gc, TURNRATE, SLOWTURNRATE, LINEARRATE, advancedegrees, Z)
    gc.write('M99\n')
    gc.write('\n')

    ######################################
    # main groove subroutine start point #
    ######################################
    gc.write('O1000\n')
    gc.write('M8\n')
    gc.write('G1 F'+repr(RATE)+' A0 Z'+'%.3f'%Zfwd[0]+'\n')
    gc.write('G4 P1 (PAUSE TO CHECK ROTARY TABLE)\n')
    for idx in range(numgrooves):
        groove(gc,Zfwd,Yfwd,RATE,incrgroove,idx,0)
        coolcycle(gc)
        if idx != (numgrooves-1):
            gc.write('M8\n')
            groove(gc,Zrev,Yrev,RATE,incrgroove,idx,1)
            gc.write('G4 P.1\n') #stops chatter when going to next groove
            turn(gc, TURNRATE, incrgroove, idx+1)
            gc.write('G4 P.1\n')  #additional pause for smoother transition from next groove to fwd cut
    gc.write('M99\n') # main groove subroutine end
    gc.write('\n')

    ##############################################
    # final groove return subroutine start point #
    ##############################################
    gc.write('O1005\n')
    gc.write('M8\n')
    groove(gc,Zrev,Yrev,RATE,incrgroove,idx,1)
    gc.write('G4 P.1\n') #stops chatter when going to next groove
    gc.write('M99\n') # final groove return subroutine end
    gc.write('\n')

    #######################################################
    # cut all grooves WITHOUT stop subroutine start point #
    #######################################################
    gc.write('O2000\n')
    gc.write('M98 P1000 L1\n')
    gc.write('M98 P1005 L1\n')
    gc.write('M98 P0500 L1\n')
    gc.write('M99\n') # WITHOUT stop subroutine end 
    gc.write('\n')

    ####################################################
    # cut all grooves WITH stop subroutine start point #
    ####################################################
    gc.write('O2001\n')
    gc.write('M98 P1000 L1\n')
    gc.write('M0\n')
    gc.write('M98 P1005 L1\n')
    gc.write('M98 P0500 L1\n')
    gc.write('M99\n') # WITH stop subroutine end 
    gc.write('\n')

    gc.close()

def main():
    ti = float(input('Initial twist: 1:'))
    tf = float(input('Final twist: 1:'))
    numgrooves = int(input('Number of grooves: '))
    stockL = float(input('Stock length in inches: '))
    rifleL = float(input('Final rifled length in inches: '))
    startrifleL = float(input('Distance from start of stock to start of rifling: '))
    startcutterL = float(input('Cutter start airgap in inches: '))
    endcutterL = float(input('Cutter end airgap in inches: '))
    zprec = float(input('Desired precision (linear step size in inches): '))
    rate = int(input('Feed rate: '))
    turnrate = int(input('Turn rate: '))
    advancedegrees = float(input('Advance angle (degrees): '))
    filename = input('G-code file name: ')
    comments = input('Enter comments: ')
    beforerifleL = startcutterL+startrifleL
    afterrifleL = stockL-startrifleL+endcutterL
    Zcalc = np.arange(-(beforerifleL), afterrifleL+zprec, zprec) 
    Ycalc = gaintwist(ti, tf, rifleL, Zcalc)
    Y = Ycalc - min(Ycalc)
    Z = Zcalc - min(Zcalc)
    gcodegen(filename, Z, Y, numgrooves, rate, turnrate, advancedegrees, comments)

if __name__ == '__main__':
    main()