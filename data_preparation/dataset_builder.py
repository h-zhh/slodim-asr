import os
import re
from pydub import AudioSegment
from typing import List, Tuple
import pandas as pd
from sklearn.model_selection import train_test_split
from pympi import Elan
import librosa
import soundfile as sf
import json


class DatasetBuilder:
    def __init__(self, eaf_dir, wav_dir, seg_dir, output_dir, split=True, test_size=0.1):
        self.eaf_dir = eaf_dir
        self.wav_dir = wav_dir
        self.seg_dir = seg_dir
        self.output_dir = output_dir
        self.test_size = test_size
        self.split = split

    def _parse_root_id_and_session(self, filename: str) -> Tuple[str, str]:
        '''
        parse root id and session number from filname
        '''
        pattern = r"([a-zA-Z]+-\d+)-(\d)\.eaf"
        match = re.match(pattern, filename, re.IGNORECASE)

        if match:
            root_id = match.group(1).upper()
            session = match.group(2)
            return root_id, session
        else:
            print(f"Warning: {filename} root id and session not found")
            return None, None

    def _write_json(self, data, file_path):
        '''
        write dataset into csv file
        '''
        with open(file_path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def parse_eaf_file(self, eaf_path: str) -> List[Tuple[int, int, str]]:
        '''
        parse eaf file for annotations
        '''
        eaf = Elan.Eaf(eaf_path)
        annotations = []

        for tier in eaf.get_tier_ids_for_linguistic_type("verbatim"):
            for annotation in eaf.get_annotation_data_for_tier(tier):
                start_time, end_time, text = annotation
                annotations.append((start_time, end_time, text))

        return annotations
    
    def slice_and_process_audio(self, wav_path: str, seg_path: str, start_time: int, end_time: int):
        '''
        slice audio segments according to annotations
        '''
        target_sampling_rate = 16000

        audio = AudioSegment.from_wav(wav_path)
        segment = audio[start_time:end_time]
        segment.export(seg_path, format="wav")
        audio_data, sampling_rate = librosa.load(seg_path, sr=None)
        
        # Check if the input signal length is 0
        if len(audio_data) == 0:
            print(f"Deleting {seg_path} due to zero-length input signal")
            os.remove(seg_path)
            return None

        # Resample audio to the target sampling rate
        if sampling_rate != target_sampling_rate:
            audio_data = librosa.resample(audio_data, orig_sr=sampling_rate, 
                                          target_sr=target_sampling_rate)

        # Save resampled audio to the original file
        sf.write(seg_path, audio_data, target_sampling_rate, format='wav')

        # Convert NumPy array to list
        audio_data_list = audio_data.tolist()
        return audio_data_list

    def build_dataset(self):
        '''
        build dataset and split train and test set
        '''
        os.makedirs(self.seg_dir, exist_ok=True)
        data = []
        
        for idx, eaf_file in enumerate(os.listdir(self.eaf_dir)):
            root_id, session = self._parse_root_id_and_session(eaf_file)
            wav_filename = f"{root_id}-{session}.wav"
            wav_path = os.path.join(self.wav_dir, wav_filename)

            if os.path.exists(wav_path):
                # parse eaf file
                eaf_path = os.path.join(self.eaf_dir, eaf_file)
                annotations = self.parse_eaf_file(eaf_path)
                seg_folder = os.path.join(self.seg_dir, os.path.splitext(eaf_file)[0])
                os.makedirs(seg_folder, exist_ok=True)

                # write dataset into a list of dictionaries
                for start_time, end_time, text in annotations:
                    seg_path = os.path.join(seg_folder, f"{start_time}-{end_time}.wav")
                    waveform = self.slice_and_process_audio(wav_path, seg_path, start_time, end_time)
                    data.append({
                        "path": seg_path, 
                        "transcription": text, 
                        "waveform": waveform, 
                        "sampling_rate": 16000, 
                        "duration": end_time - start_time, 
                        "conversation_id": root_id
                        })
            else:
                print(f"Warning: Audio file '{wav_filename}' not found.")
            
            if (idx + 1) % 10 == 0:
                print(f"{idx + 1} files built into dataset")

        print(f"wav folder size: {len(os.listdir(self.wav_dir))}")
        print(f"eaf folder size: {len(os.listdir(self.eaf_dir))}")
        print(f"Dataset size: {len(data)}")
        if len(data) == 0:
            print("Error: The dataset is empty. Please check your input directories and files.")
            return None, None
        
        train_data, test_data = train_test_split(data, test_size=self.test_size, random_state=42)
        self._write_json(train_data, os.path.join(self.output_dir, "train.json"))
        self._write_json(test_data, os.path.join(self.output_dir, "test.json"))
        print(f"Dataset has been written into {self.output_dir}")

if __name__ == "__main__":
    eaf_dir = "./eaf"
    wav_dir = "./audio/wav"
    seg_dir = "./audio/seg"
    output_dir = "./dataset"

    # Instantiate the DatasetBuilder class
    dataset_builder = DatasetBuilder(eaf_dir, wav_dir, seg_dir, output_dir)

    # Build the dataset by creating the segments and generating train and test CSV files
    dataset_builder.build_dataset()