import pandas as pd
import re
import time
import numpy as np
import pygame
from scipy import signal as sig
from pythonosc import udp_client

#reading in the data
df = pd.read_csv('vie-bdl-ecl-wea-1872f.csv', sep=';')

df.head()

# substituting , with . and convert to floats
df['T'].replace(',', '.', regex=True, inplace=True)

df['T'] = df['T'].astype('float')

old_min, old_max = df['T'].min(), df['T'].max()
new_min, new_max = 0, 1

# define the rescaling function
rescale = lambda x: (x - old_min) * (new_max - new_min) / (old_max - old_min) + new_min

#interpolating values between 0 and 1 for individual purpose scaling later
df['Rescale_T'] = df['T'].apply(rescale)

# set up audio stuff

# defining the samplerate

global sr
sr = 44100


# all the sounds

def low_tone(frq, dur):
    line = np.linspace(0, 1, int((sr / 1000) * dur))
    line2 = np.sqrt(line)
    line3 = line2 * frq - 0.15
    line4 = np.cos(line3)
    envexp = 0.5 ** (25 * line)
    kick = line4 * envexp
    sos = sig.butter(2, 300, 'lp', analog=False, fs=1000, output='sos')
    filtered = sig.sosfilt(sos, kick)
    return filtered


def high_tone(frq, dur):
    line = np.linspace(0, 1, int((sr / 1000) * dur))
    t = np.arange(int((sr / 1000) * dur)) / sr
    envexp = 0.5 ** (25 * line)
    sine = 1 * np.sin(2 * np.pi * frq * t) * envexp
    return sine


def impulse_sound(freq, dur):
    line = np.linspace(0, 1, int((sr / 1000) * dur))
    t = np.arange(int((sr / 1000) * dur)) / sr
    envexp = 0.5 ** (25 * line)
    sine = 1 * np.sin(2 * np.pi * freq * t) * envexp
    sos = sig.butter(2, 200, 'hp', analog=False, fs=1000, output='sos')
    filtered = sig.sosfilt(sos, sine)
    return filtered


def mid_tone(freq, dur, fm_am, fm_ratio, amp):
    line = np.linspace(0, 1, int((sr / 1000) * dur))
    t = np.arange(int((sr / 1000) * dur)) / sr
    line_up = np.linspace(0, amp, int((sr / 1000) * dur * 0.5))
    line_down = np.linspace(amp, 0, int((sr / 1000) * dur - len(line_up)))
    envelope = np.concatenate([line_up, line_down])
    sine_mod = 1 * np.sin(2 * np.pi * (freq * fm_ratio) * t) * envelope
    sine_carrier = 1 * np.sin(2 * np.pi * (freq + sine_mod * fm_am) * t) * envelope
    return sine_carrier


# function for turning arrays in pygame-sound-objects

def conv(soundarr):
    sound = np.array([32767 * soundarr, 32767 * soundarr]).T.astype(np.int16)
    sound = pygame.sndarray.make_sound(sound.copy())
    sound.set_volume(0.1)
    return sound


# initializing the mixer
pygame.mixer.pre_init(44100, size=-16, channels=2)
pygame.mixer.init()
pygame.mixer.set_num_channels(32)


# set up an OSC client for visuals in pure data
client = udp_client.SimpleUDPClient('localhost', 8000)

# sonificaiton loop

first_year = df['REF_YEAR'].min()
off = 0
mean_note = 0.5


for i in df.index:
    # determine highest and lowest temperature and year
    low_trig = df[df['REF_YEAR'] == first_year + off]['T'].min()
    high_trig = df[df['REF_YEAR'] == first_year + off]['T'].max()
    year = int(df['REF_YEAR'][i])
    # search for mean temp of year and trigger intervall tone
    # the higher the mean temperature the more modulated
    # and longer the tone gets
    if i > 0 and df['REF_YEAR'][i - 1] < df['REF_YEAR'][i]:
        mean_temp = df[df['REF_YEAR'] == first_year + off]['Rescale_T'].median()
        mean_note = df[df['REF_YEAR'] == first_year + off]['Rescale_T'].median()
        conv(mid_tone(100, 1200 * mean_temp, mean_temp,
                      10 * mean_temp, mean_temp) * 0.65).play()
    # trigger low_tone on
    if df['T'][i] == low_trig:
        conv(low_tone(300, 1000) * 0.6).play()
        l_msg = 1
    else:
        l_msg = 0
    # trigger high tone when highest temp is reached
    if df['T'][i] == high_trig:
        conv(high_tone(1000, 1000) * 0.48).play()
        h_msg = 1
    else:
        h_msg = 0
    # trigger impulse sound
    conv(impulse_sound(df['Rescale_T'][i] * 10000 + 2000, 15)
                       * df['Rescale_T'][i] * 1.1).play()
    vol_msg = df['Rescale_T'][i]
    client.send_message('/viz/control', [vol_msg, l_msg, h_msg, mean_note, year])
    time.sleep(0.1)
    if df['REF_YEAR'][(i + 1) % len(df.index)] > df['REF_YEAR'][i]:
        off += 1


# shut viz off
client.send_message('/sound/control', [0, 0, 0, 0, 0])
