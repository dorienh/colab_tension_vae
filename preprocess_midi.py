import pretty_midi
import numpy as np
from params import *



def beat_time(pm, beat_division=4):
    beats = pm.get_beats()

    divided_beats = []
    for i in range(len(beats) - 1):
        for j in range(beat_division):
            divided_beats.append((beats[i + 1] - beats[i]) / beat_division * j + beats[i])
    divided_beats.append(beats[-1])
    down_beats = pm.get_downbeats()
    down_beat_indices = []
    for down_beat in down_beats[:-1]:
        down_beat_indices.append(np.argwhere(divided_beats == down_beat)[0][0])

    return np.array(divided_beats),np.array(down_beat_indices)


def find_active_range(rolls, down_beat_indices):

    if down_beat_indices[1] - down_beat_indices[0] == 8:
        interval = SEGMENT_BAR_LENGTH*2
        SAMPLES_PER_BAR = 8
    elif down_beat_indices[1] - down_beat_indices[0] == 16:
        interval = SEGMENT_BAR_LENGTH
        SAMPLES_PER_BAR = 16
    else:
        return None

    track_filled = []
    for roll in rolls:
        bar_filled = []
        for bar_index in down_beat_indices:
            bar_filled.append(np.count_nonzero(roll[:,bar_index:bar_index+SAMPLES_PER_BAR]) > 0)
        track_filled.append(bar_filled)

    track_filled = np.array(track_filled)
    two_track_filled_bar = np.count_nonzero(track_filled[:2,:], axis=0) == 2
    filled_indices = []

    for i in range(0,len(two_track_filled_bar)-interval,SLIDING_WINDOW):
        if np.sum(two_track_filled_bar[i:i+interval]) == interval:
            filled_indices.append((i,i+interval))

    return filled_indices


def stack_data(rolls):
    melody_roll,bass_roll = rolls
    new_bass_roll = np.zeros((12, bass_roll.shape[1]))
    bass_start_roll_new = np.zeros((1, bass_roll.shape[1]))
    bass_empty_roll = np.zeros((1, bass_roll.shape[1]))

    for step in range(bass_roll.shape[1]):
        pitch = np.where(bass_roll[:, step] != 0)[0] % 12
        original_pitch = np.where(bass_roll[:, step] != 0)[0]

        if len(pitch) > 0:
            for i in pitch:
                new_pitch = i
                new_bass_roll[new_pitch, step] = 1

            # a note start
            if bass_roll[original_pitch, step] == 1:
                bass_start_roll_new[:, step] = 1
        else:
            bass_empty_roll[:, step] = 1

    new_melody_roll = np.zeros((73,melody_roll.shape[1]))
    melody_start_roll_new = np.zeros((1, melody_roll.shape[1]))
    melody_empty_roll = np.zeros((1, melody_roll.shape[1]))

    for step in range(melody_roll.shape[1]):
        pitch = np.where(melody_roll[:, step] != 0)[0]

        if len(pitch) > 0:

            original_pitch = pitch[0]
            new_pitch = pitch[0]
            shifted_pitch = new_pitch - 24

            if 0 <= shifted_pitch <= 72:
                new_melody_roll[shifted_pitch, step] = 1

                # a note start
                if melody_roll[original_pitch, step] == 1:
                    # if step > 0:
                    melody_start_roll_new[:,step] = 1

        else:
            melody_empty_roll[:, step] = 1

    concatenated_roll = np.concatenate([new_melody_roll,melody_empty_roll,melody_start_roll_new,
                                        new_bass_roll,bass_empty_roll,bass_start_roll_new])
    return concatenated_roll.transpose()

def prepare_one_x(roll_concat,filled_indices,down_beat_indices):

    rolls = []
    for start,end in filled_indices:
        start_index = down_beat_indices[start]
        end_index = down_beat_indices[end]
        # select 4 bars
        if roll_concat[start_index:end_index, :].shape[0] != (SAMPLES_PER_BAR * SEGMENT_BAR_LENGTH):
            print('skip')
            continue

        rolls.append(roll_concat[start_index:end_index,:])

    return rolls, filled_indices


def get_roll_with_continue(track_num, track,times):
    if track.notes == []:
        return np.array([[]] * 128)

    # 0 for no note, 1 for new note, 2 for continue note
    snap_ratio = 0.5

    piano_roll = np.zeros((128, len(times)))

    previous_end_step = 0
    previous_start_step = 0
    previous_pitch = 0
    for note in track.notes:

        time_step_start = np.where(note.start >= times)[0][-1]

        if note.end > times[-1]:
            time_step_stop = len(times) - 1
        else:
            time_step_stop = np.where(note.end <= times)[0][0]

        # snap note to the grid
        # snap start time step
        if time_step_stop > time_step_start:
            start_ratio = (times[time_step_start+1] - note.start) / (times[time_step_start+1] - times[time_step_start])
            if start_ratio < snap_ratio:
                if time_step_stop - time_step_start > 1:
                    time_step_start += 1
        # snap end time step
            end_ratio = (note.end - times[time_step_stop-1]) / (times[time_step_stop] - times[time_step_stop-1])
            if end_ratio < snap_ratio:
                if time_step_stop - time_step_start > 1:
                    time_step_stop -= 1

        if track_num == 0:
            # melody track, ensure single melody line
            if previous_start_step > time_step_start:
                continue
            if previous_end_step == time_step_stop and previous_start_step == time_step_start:
                continue
            piano_roll[note.pitch, time_step_start] = 1
            piano_roll[note.pitch, time_step_start + 1:time_step_stop] = 2

            if time_step_start < previous_end_step:
                piano_roll[previous_pitch, time_step_start:] = 0
            previous_pitch = note.pitch
            previous_end_step = time_step_stop
            previous_start_step = time_step_start

        elif track_num == 1:
            # for bass, select the lowest pitch if the time range is the same
            if previous_end_step == time_step_stop and previous_start_step == time_step_start:
                continue
            if previous_start_step > time_step_start:
                continue
            if time_step_start < previous_end_step:
                piano_roll[previous_pitch, time_step_start:] = 0
            piano_roll[note.pitch, time_step_start] = 1
            piano_roll[note.pitch, time_step_start + 1:time_step_stop] = 2

            previous_pitch = note.pitch
            previous_end_step = time_step_stop
            previous_start_step = time_step_start
        else:
            piano_roll[note.pitch, time_step_start:time_step_stop] = 1

    return piano_roll


def get_piano_roll(pm,sample_times):
    """

    :param pm: pretty midi piano roll with at least 3 tracks
    :return: three piano rolls
    melody mono
    bass mono
    """
    rolls = []


    for track_num in range(2):
        rolls.append(get_roll_with_continue(track_num, pm.instruments[track_num],times=sample_times))
    return rolls


def preprocess_midi(midi_file):

    pm = pretty_midi.PrettyMIDI(midi_file)

    if len(pm.instruments) < 2:
        print('track number < 2, skip')
        return

    sixteenth_time, down_beat_indices = beat_time(pm, beat_division=int(SAMPLES_PER_BAR / 4))
    rolls = get_piano_roll(pm, sixteenth_time)

    melody_roll = rolls[0]
    bass_roll = rolls[1]

    filled_indices = find_active_range([melody_roll, bass_roll], down_beat_indices)

    if filled_indices is None:
        print('not enough data for melody and bass track')
        return None
    roll_concat = stack_data([melody_roll, bass_roll])

    x,indices = prepare_one_x(roll_concat, filled_indices, down_beat_indices)

    return np.array(x),indices,pm


# midi_folder = '/Users/ruiguo/Downloads/dataset/lmd/output_1001'
#
# for path, subdirs, files in os.walk(midi_folder):
#     for name in files:
#         if name[-3:].lower() == 'mid':
#             key_file = json.load(open('/Users/ruiguo/Downloads/tension_vae/two_track_no_mode_change' + '/files_result.json','r'))
#             # print(key_file)
#             tension_folder = '/home/data/guorui/two_track_no_mode_change'
#             tension_path = path.replace(midi_folder, tension_folder)
#             tension_name = tension_path + '/' + name[:-4]
#
#             print(f'working on file {tension_name}')
#             if tension_name not in key_file:
#                 continue
#             key = key_file[tension_name][0]
#
#             key_change_bar = key_file[tension_name][1]
#             if key !='major C' and key != 'minor A':
#                 continue
#             tension_name = tension_name.replace('/home/data/guorui/', '')

# def four_bar_interate(pianoroll, model, first_vector, second_vector, third_vector):
#     number_of_iteration = pianoroll
#     if pianoroll is None:
#         z = np.random.normal(size=(1, z_dim))
#     else:
#         z = model.layers[1].predict(pianoroll)
#     #     z = z-np.mean(z)
#
#
#     changed_z_up = z + np.random.uniform(5, 7) * vector_up_t
#
#     changed_reconstruction_up = vae.layers[2].predict(changed_z_up)
#
#     changed_recon_result_up = result_sampling(np.concatenate(list(changed_reconstruction_up), axis=-1))[0]
#
#     changed_tensile_reconstruction_up = changed_reconstruction_up[-2]
#     changed_diameter_reconstruction_up = changed_reconstruction_up[-1]
#
#     changed_tensile_up = np.squeeze(changed_tensile_reconstruction_up)
#     changed_diameter_up = np.squeeze(changed_diameter_reconstruction_up)
#
#     #     draw_two_figure(tensile_reconstruction,changed_tensile_up,'original tensile',
#     #                     'changed tensile','16bar_tensile_up.png','tensile strain','Tension shape going up',
#     #                     True)
#
#     changed_z_down = z - random.uniform(5, 7) * vector_up_t
#
#     changed_reconstruction_down = vae.layers[2].predict(changed_z_down)
#
#     changed_recon_result_down = result_sampling(np.concatenate(list(changed_reconstruction_down), axis=-1))[0]
#
#     changed_tensile_reconstruction_down = changed_reconstruction_down[-2]
#     changed_diameter_reconstruction_down = changed_reconstruction_down[-1]
#     changed_tensile_down = np.squeeze(changed_tensile_reconstruction_down)
#     changed_diameter_down = np.squeeze(changed_diameter_reconstruction_down)
#
#     #     draw_two_figure(tensile_reconstruction,changed_tensile_down,'original tensile',
#     #                     'changed tensile','16bar_tensile_down.png','tensile strain','Tension shape going down',
#     #                     True)
#
#     print(np.concatenate([changed_tensile_up, changed_tensile_down]).shape)
#
#     changed_z_high = z + random.uniform(3, 4) * vector_high_d + np.random.uniform(4, 6) * vector_up_t
#
#     changed_reconstruction_high = vae.layers[2].predict(changed_z_high)
#
#     changed_recon_result_high = result_sampling(np.concatenate(list(changed_reconstruction_high), axis=-1))[0]
#
#     changed_tensile_reconstruction_high = changed_reconstruction_high[-2]
#
#     changed_diameter_reconstruction_high = changed_reconstruction_high[-1]
#
#     changed_tensile_high = np.squeeze(changed_tensile_reconstruction_high)
#
#     changed_diameter_high = np.squeeze(changed_diameter_reconstruction_high)
#
#     #     draw_two_figure(diameter_reconstruction,changed_diameter_high,'original diameter',
#     #                     'changed diameter','16bar_diameter_high.png','cloud diameter','Cloud diameter level high',
#     #                     True)
#
#     changed_z_low = z - random.uniform(3, 4) * vector_high_d - np.random.uniform(4, 6) * vector_up_t
#
#     changed_reconstruction_low = vae.layers[2].predict(changed_z_low)
#
#     changed_recon_result_low = result_sampling(np.concatenate(list(changed_reconstruction_low), axis=-1))[0]
#
#     changed_tensile_reconstruction_low = changed_reconstruction_low[-2]
#
#     changed_diameter_reconstruction_low = changed_reconstruction_low[-1]
#     changed_tensile_low = np.squeeze(changed_tensile_reconstruction_low)
#
#     changed_diameter_low = np.squeeze(changed_diameter_reconstruction_low)
#
#     #     draw_two_figure(diameter_reconstruction,changed_diameter_low,'original diameter',
#     #                     'changed diameter','16bar_diameter_low.png','cloud diameter','Cloud diameter level low',
#     #                     True)
#
#     result_roll = np.vstack([changed_recon_result_up, changed_recon_result_down,
#                              changed_recon_result_high, changed_recon_result_low])
#     all_tensile_connected = np.concatenate([changed_tensile_up,
#                                             changed_tensile_down,
#                                             changed_tensile_high,
#                                             changed_tensile_low])
#     all_diameter_connected = np.concatenate([changed_diameter_up,
#                                              changed_diameter_down,
#                                              changed_diameter_high,
#                                              changed_diameter_low])
#     #     draw_two_figure(all_tensile_connected,all_diameter_connected,
#     #                    'tensile strain',
#     #                     'diameter','16_bar.png','tensile and cloud diameter','16 bar tensile strain and cloud diameter',
#     #                     True)
#
#     return [roll_to_midi_0129(result_roll),
#             z]



