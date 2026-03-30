import argparse
import yaml
import os
import sys
import numpy as np
from scipy.interpolate import CubicSpline

# interpret command line arguments
parser = argparse.ArgumentParser(description='G-code config parameters')
parser.add_argument('-c','--config', help='Configuration file', default=None)
parser.add_argument('-o','--output', help='Output file name', default=None)
parser.add_argument('-m','--message', help='Optional comment message', default=None)
parser.add_argument('-p','--plot', help='Plot the rifling cut', action='store_true', default=False)
args = parser.parse_args()

def gain_twist(output_type, gaintype, ti, tf, zprec, rifleL, startnogainL, endnogainL,
        start_cut_z, end_cut_z, start_rifling_z, end_rifling_z):
    z_calc = np.arange(start_cut_z, end_cut_z+zprec, zprec)
    twist_calc = z_calc.copy()
    start_gain_z = start_rifling_z+startnogainL
    end_gain_z = end_rifling_z-endnogainL
    twist_calc[z_calc<start_gain_z] = ti
    twist_calc[z_calc>end_gain_z] = tf
    if gaintype == 'linear':
        bc_type = 'not-a-knot'
    elif gaintype == 'sinusoid':
        bc_type = 'clamped'
    else:
        raise RuntimeError('Invalid gain twist type!')
    twist_interp = CubicSpline([start_gain_z,end_gain_z],
        [ti,tf], bc_type=bc_type)
    rifling_idxs = (z_calc>=start_gain_z)&(z_calc<=end_gain_z)
    twist_calc[rifling_idxs] = twist_interp(z_calc[rifling_idxs])

    if output_type == 'twist':
        y_calc = twist_calc
    elif output_type == 'angle_per_step':
        y_calc = twist_to_angle(twist_calc, zprec)
    elif output_type == 'accumulated_angle':
        y_calc = np.cumsum(twist_to_angle(twist_calc, zprec))
        y_calc = y_calc-y_calc[0]

    return z_calc, y_calc

# twist is 1:inches (360 degrees : inches)
def twist_to_angle(twist, zprec):
    return zprec*360/twist

def plot_rifling(Z, Y, start_rifling_z, end_rifling_z, startnogainL, endnogainL):
    import matplotlib.pyplot as plt
    y_min, y_max = Y.min(), Y.max()
    plt.plot([start_rifling_z,start_rifling_z],[y_min,y_max],'grey','--')
    plt.plot([end_rifling_z,end_rifling_z],[y_min,y_max],'grey')
    plt.plot([start_rifling_z+startnogainL,start_rifling_z+startnogainL],[y_min,y_max],'red')
    plt.plot([end_rifling_z-endnogainL,end_rifling_z-endnogainL],[y_min,y_max],'red')
    plt.plot(Z, Y, 'black')
    plt.title('unwrapped rifling cut')
    plt.xlabel('barrel position (inches)')
    plt.ylabel('angle (degrees)')
    plt.yticks(np.arange(0,180*np.ceil(Y.max()/180)+1,180),
        np.arange(0,180*np.ceil(Y.max()/180)+1,180).astype(int))
    plt.show()

def plot_rifling_debug(Z, Y, Y_linear, Y_twist, Y_per_step, Y_per_step_linear, start_rifling_z, end_rifling_z, startnogainL, endnogainL):
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    f = plt.figure()
    gs = gridspec.GridSpec(5,1)

    ax1 = plt.subplot(gs[0])
    ax2 = plt.subplot(gs[1])
    ax3 = plt.subplot(gs[2])
    ax4 = plt.subplot(gs[3])
    ax5 = plt.subplot(gs[4])

    ax1.plot(Z, Y_twist, 'black')
    ax1.set_title('twist rate')
    ax1.set_yticks([Y_twist[0],Y_twist[-1]])
    ax1.set_ylabel('twist (1:X)')

    ax2.plot(Z, Y_per_step, 'black')
    Z_step = Z[1]-Z[0]
    ax2.set_title(f'angle per step ({Z_step:.3f}in)')
    ax2.set_yticks(np.linspace(Y_per_step[0],Y_per_step[-1],5))
    ax2.set_ylabel('angle (deg)')

    y_min, y_max = Y.min(), Y.max()
    ax3.plot([start_rifling_z,start_rifling_z],[y_min,y_max],'grey','--')
    ax3.plot([end_rifling_z,end_rifling_z],[y_min,y_max],'grey')
    ax3.plot([start_rifling_z+startnogainL,start_rifling_z+startnogainL],[y_min,y_max],'red')
    ax3.plot([end_rifling_z-endnogainL,end_rifling_z-endnogainL],[y_min,y_max],'red')
    ax3.plot(Z, Y, 'black')
    ax3.set_ylabel('angle (deg)')
    ax3.set_yticks(np.arange(0,180*np.ceil(Y.max()/180)+1,180),
        np.arange(0,180*np.ceil(Y.max()/180)+1,180).astype(int))
    ax3.set_title('unwrapped rifling cut')

    # backcalc_twist = 1/np.diff(np.round(Y,3),prepend=-Y[1])*360*Z_step
    # backcalc_twist_error = Y_twist-backcalc_twist
    # ax4.plot(Z, backcalc_twist_error, color='grey',linewidth=0.5)
    # ax4.set_title('twist quantization error')
    # ax4.set_ylabel('twist err (1:X)')

    diff_angle = Y-Y_linear
    ax4.plot((Z[0],Z[-1]), [0,0], color='grey',linewidth=2.0)
    ax4.plot(Z, diff_angle, color='red')
    ax4.set_title('difference from linear (accumulated angle)')
    ax4.set_ylabel('angle (deg)')

    diff_angle_per = Y_per_step-Y_per_step_linear
    ax5.plot((Z[0],Z[-1]), [0,0], color='grey',linewidth=2.0)
    ax5.plot(Z, diff_angle_per, color='red')
    ax5.set_title('difference from linear gain (incremental)')
    ax5.set_ylabel('angle (deg)')
    ax5.set_xlabel('barrel position (inches)')

    plt.tight_layout()
    plt.show()

def cool_cycle(f):
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

def turn(f, rate, incrgroove, grooveidx):
    f.write('G1 F'+repr(rate)+' A'+repr(incrgroove*grooveidx)+'\n')

def advance_cutter(f, turnrate, slowturnrate, linearrate, advancedegrees, Z):
    f.write('G1 F'+repr(turnrate)+' A'+repr(round(advancedegrees,3))+' (adjust A__ for cutter height)\n')
    f.write('G1 F'+repr(linearrate)+' Z'+repr(round(-0.5,3))+'\n')
    f.write('G1 F'+repr(slowturnrate)+' A0\n')
    f.write('G1 F'+repr(linearrate)+' Z'+repr(round(0,3))+'\n')

def gcode_gen(filename, configname, Z, Y, numgrooves, rate, turnrate,
        slowturnrate, linearrate, advancedegrees, comments):
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
    gc.write('(filename: '+filename+'.nc)\n')
    gc.write('(config: ./config/'+configname+'.yml)\n')
    gc.write('(comments: '+comments+')\n')
    # Main Program Start
    gc.write('G17 G20 G40 G49 G64 G80 G90\n')
    gc.write('#1 = 0 (variable monitor for cycle count)\n')
    gc.write('M98 P2000 L5 (adjust L__ for N-1 cycles)\n') # Subroutine L value is number of cycles
    gc.write('M98 P2001 L1\n') 
    gc.write('M30\n') # Main Program Stop
    gc.write('\n')

    # O1000: main groove subroutine (does N grooves forward, N-1 grooves backwards)
    # O1005: final groove return subroutine (does Nth groove backwards)
    # O2000: main groove + final groove subroutine (no stop)
    # O2001: main groove + final groove subroutine (M0 stop before final groove return)

    #########################################
    # advance cutter subroutine start point #
    #########################################
    gc.write('O0500\n')
    advance_cutter(gc, TURNRATE, SLOWTURNRATE, LINEARRATE, advancedegrees, Z)
    gc.write('M99\n')
    gc.write('\n')

    ######################################
    # main groove subroutine start point #
    ######################################
    gc.write('O1000\n')
    gc.write('M8\n')
    gc.write('G1 F'+repr(RATE)+' A0 Z'+'%.3f'%Zfwd[0]+'\n')
    gc.write('G4 P1 (PAUSE TO CHECK ROTARY TABLE)\n')
    gc.write('#1 = [#1+1] (variable monitor for cycle count)\n')
    for idx in range(numgrooves):
        groove(gc,Zfwd,Yfwd,RATE,incrgroove,idx,0)
        cool_cycle(gc)
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
    if args.config is not None:
        config_name = args.config
    else:
        config_name = input('Config name (./config/"_____".yml): ')
    config_dir = os.path.join('config',config_name+'.yml')
    try:
        with open(config_dir) as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
    except:
        print('WARNING:')
        print('Configuration file '+config_name+'.yml not found')
        sys.exit(1)

    if args.output is not None:
        output_filename = args.output
    else:
        output_filename = input('Output file (./gcode/"_____".nc): ')

    output_path = os.path.join('./gcode/',output_filename)
    if output_filename != 'demo':
        if os.path.exists(output_path+'.nc'):
            print('WARNING:')
            print('Output file '+output_path+'.nc already exists!')
            print('Aborting...')
            sys.exit(1)

    if args.message is not None:
        comments = args.message
    else:
        comments = input('Commments (press enter to generate G-Code): ')

    gaintype = config['gaintype']
    ti = config['ti']
    tf = config['tf']
    numgrooves = config['numgrooves']
    stockL = config['stockL']
    rifleL = config['rifleL']
    startnogainL = config['startnogainL']
    endnogainL = config['endnogainL']
    startrifleL = config['startrifleL']
    startcutterL = config['startcutterL']
    endcutterL = config['endcutterL']
    zprec = config['zprec']
    rate = config['rate']
    turnrate = config['turnrate']
    slowturnrate = config['slowturnrate']
    linearrate = config['linearrate']
    advancedegrees = config['advancedegrees']

    start_cut_z = 0
    end_cut_z = startcutterL+stockL+endcutterL
    start_rifling_z = startcutterL+startrifleL
    end_rifling_z = start_rifling_z+rifleL

    z_calc, y_calc = gain_twist('accumulated_angle', gaintype, ti, tf, zprec, rifleL, startnogainL, endnogainL,
        start_cut_z, end_cut_z, start_rifling_z, end_rifling_z)

    _, y_calc_linear = gain_twist('accumulated_angle', 'linear', ti, tf, zprec, rifleL, startnogainL, endnogainL,
        start_cut_z, end_cut_z, start_rifling_z, end_rifling_z)
    _, y_twist = gain_twist('twist', gaintype, ti, tf, zprec, rifleL, startnogainL, endnogainL,
        start_cut_z, end_cut_z, start_rifling_z, end_rifling_z)
    _, y_per_step = gain_twist('angle_per_step', gaintype, ti, tf, zprec, rifleL, startnogainL, endnogainL,
        start_cut_z, end_cut_z, start_rifling_z, end_rifling_z)
    _, y_per_step_linear = gain_twist('angle_per_step', 'linear', ti, tf, zprec, rifleL, startnogainL, endnogainL,
        start_cut_z, end_cut_z, start_rifling_z, end_rifling_z)

    gcode_gen(output_path, config_name, z_calc, y_calc, numgrooves, rate, turnrate, 
        slowturnrate, linearrate, advancedegrees, comments)

    if args.plot:
        plot_rifling_debug(z_calc, y_calc, y_calc_linear, y_twist, y_per_step, y_per_step_linear, start_rifling_z, end_rifling_z, startnogainL, endnogainL)

if __name__ == '__main__':
    main()
