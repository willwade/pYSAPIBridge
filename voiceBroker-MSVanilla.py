import pythoncom
import winreg 
import win32com.client
import win32com.server.register
import azure.cognitiveservices.speech as speechsdk
import time
import io
import json
import logging

logging.basicConfig(filename='VoiceBroker.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class VoiceBroker:
    _public_methods_ = ['Speak', 'Pause', 'Resume', 'GetVoices', 'SetVoice', 'SetInterest', 'WaitForNotifyEvent']
    _reg_progid_ = "VoiceBroker.Application"
    _reg_clsid_ = pythoncom.CreateGuid()  # Generates a new CLSID, or use pythoncom.CreateGuid() to generate one and hard-code it here

    def __init__(self, register=True):
        logging.debug(f"[init] running")
        logging.debug(f"[init] get creds")
        self.get_credentials('credentials.json')
        # Initialize the COM library within the class
        pythoncom.CoInitialize()
        # Create an instance of the SAPI SpVoice COM object
        self.sp_voice = win32com.client.Dispatch("SAPI.SpVoice")
        microsoft_creds = self.credentials['Microsoft']
        self.speech_config = speechsdk.SpeechConfig(subscription=microsoft_creds['TOKEN'], region=microsoft_creds['region'])
        self.audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
        self.speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=self.speech_config, audio_config=self.audio_config)
        self.event_interests = {}
        self.current_voice = 'en-US-JessaNeural'
        logging.debug(f"[init] end")
        # You wouldnt usually do this - it would be done on install but Im being lazy
        if register:
            self.register_app()        
        else:
            self.unregister_com_server()
            self.unregister_sapi_entries()

    def get_credentials(self,file_path):
        try:
            with open(file_path, 'r') as file:
                self.credentials = json.load(file)
        except FileNotFoundError:
            logging.debug("The specified credentials file was not found.")
            return None
        except json.JSONDecodeError:
            logging.debug("Error decoding JSON from the credentials file.")
            return None

    def Speak(self, text):
        logging.debug(f"[Speak] Start with text: {text}")
        try:
            result = self.speech_synthesizer.speak_text_async(text).get()
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logging.info("Speech synthesis completed successfully.")
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                logging.error(f"Speech synthesis canceled: {cancellation_details.reason}")
                logging.error(f"Error details: {cancellation_details.error_details}")
        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")

    def play_audio(self, stream):
        logging.debug("[play_audio] Start")
        try:
            audio_buffer = bytearray()  # Maintaining a mutable overall buffer
            
            # Use a temporary mutable buffer for each chunk read
            chunk_size = 1024  # Define the size of each chunk to read
            while True:
                chunk = bytearray(chunk_size)  # Initialize a fresh bytearray for each read
                num_bytes = stream.read_data(chunk)  # Read into the bytearray
                
                if num_bytes == 0:
                    break  # If no bytes were read, the stream is exhausted
    
                audio_buffer.extend(chunk[:num_bytes])  # Append only the actual bytes read
    
            # Convert the accumulated bytearray to bytes for playback or further processing
            audio_bytes = bytes(audio_buffer)  # Convert bytearray to bytes
            
            # Now use `audio_bytes` with Pydub or any other audio processing library
            audio_segment = AudioSegment(
                data=audio_bytes, 
                sample_width=2,  # Adjust as per the audio data specifics
                frame_rate=16000,  # Sample rate of the audio
                channels=1  # Mono audio
            )
            play(audio_segment)  # Play the audio with Pydub
            
            logging.debug("[play_audio] Playback initiated and completed successfully.")
        except Exception as e:
            logging.error(f"General error in play_audio method: {str(e)}")
    
                        
    def Pause(self):
        pass
        #pygame.mixer.pause()  # This pauses all sounds in the mixer
    
    def Resume(self):
        pass
        #pygame.mixer.unpause()  # This resumes all paused sounds
    
    def GetVoices(self):
        try:
            result = self.speech_synthesizer.get_voices_async().get()
            voices_info = []
            for voice in result.voices:
                voice_info = f"{voice.short_name}|{voice.locale}|{voice.local_name}|{voice.gender}"
                voices_info.append(voice_info)            
            return ";".join(voices_info)
        except Exception as e:
            print(f"Failed to get voices: {str(e)}")
            return []


    def register_voices(self):
        voices = self._get_voices_dict()
        for voice in voices:
            self._register_voice(voice)

    def _get_voices_dict(self):
        result = self.speech_synthesizer.get_voices_async().get()
        return [{'name': v.short_name, 'locale': v.locale, 'gender': v.gender} for v in result.voices]

    def _register_voice(self, voice):
        """Registers each voice as a SAPI compliant voice in the Windows Registry."""
        base_key_path = "SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\"
        voice_key_name = f"{voice['name']}_{voice['locale']}"
        key_path = base_key_path + voice_key_name

        try:
            # Create or open the key path
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            winreg.SetValueEx(key, "Name", 0, winreg.REG_SZ, voice['name'])
            winreg.SetValueEx(key, "Locale", 0, winreg.REG_SZ, voice['locale'])
            winreg.SetValueEx(key, "Gender", 0, winreg.REG_SZ, voice['gender'])
            winreg.SetValueEx(key, "CLSID", 0, winreg.REG_SZ, str(self._reg_clsid_))
            winreg.CloseKey(key)
            print(f"Registered voice: {voice_key_name}")
        except Exception as e:
            print(f"Failed to register voice {voice_key_name}: {str(e)}")

    def register_app(self):
        """Registers the application as a COM server and sets up SAPI registry entries."""
        try:
            # Basic COM registration
            win32com.server.register.UseCommandLine(VoiceBroker)

            # SAPI registration for the engine
            engine_key_path = "SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\VoiceBroker"
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, engine_key_path)
            winreg.SetValueEx(key, "CLSID", 0, winreg.REG_SZ, str(self._reg_clsid_))
            winreg.SetValueEx(key, "LangDataPath", 0, winreg.REG_SZ, "path_to_language_data")
            winreg.SetValueEx(key, "VoiceDataPath", 0, winreg.REG_SZ, "path_to_voice_data")
            winreg.SetValueEx(key, "Attributes", 0, winreg.REG_SZ, "Age=Adult;Gender=Female;Language=409;")  # Customize as needed
            winreg.CloseKey(key)
            print("Application and voices registered as SAPI engine.")
        except Exception as e:
            print(f"Failed to register application as SAPI engine: {str(e)}")


    def unregister_com_server(self):
        # Unregister the classes using the win32com provided utility
        win32com.server.register.UnregisterClasses(VoiceBroker)
        
        app_name = 'VoiceBroker'
        paths = [
            r"SOFTWARE\Classes\AppID",  # Typical for 32-bit on 32-bit machines or 64-bit on 64-bit machines
            r"SOFTWARE\Wow6432Node\Classes\AppID"  # Typical for 32-bit on 64-bit machines
        ]
        total_deletions = 0
        errors = []
    
        for path in paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_ALL_ACCESS) as key:
                    subkeys = []
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            subkeys.append(subkey_name)
                            i += 1
                        except WindowsError:
                            break
    
                    for subkey_name in subkeys:
                        try:
                            subkey = winreg.OpenKey(key, subkey_name)
                            try:
                                value, _ = winreg.QueryValueEx(subkey, "AppID")
                                if value.lower() == app_name.lower():
                                    winreg.DeleteKey(key, subkey_name)
                                    print(f"Deleted {subkey_name} in {path}")
                                    total_deletions += 1
                            except FileNotFoundError:
                                pass
                            finally:
                                winreg.CloseKey(subkey)
                        except WindowsError as e:
                            errors.append(f"Failed to delete subkey {subkey_name} in {path}: {str(e)}")
    
            except WindowsError as e:
                errors.append(f"Failed to open or modify registry at {path}: {str(e)}")
    
        print(f"Total deletions: {total_deletions}")
        if errors:
            print("Errors encountered:")
            for error in errors:
                print(error)

    def unregister_sapi_entries(self):
        base_key_path = "SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens"
        engine_key_name = "VoiceBroker"
        
        try:
            engine_key_path = f"{base_key_path}\\{engine_key_name}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, engine_key_path, 0, winreg.KEY_ALL_ACCESS) as engine_key:
                # Optionally, if you had registered individual voices, remove them
                try:
                    # Assuming you had subkeys under each voice
                    num_subkeys = winreg.QueryInfoKey(engine_key)[0]
                    for i in range(num_subkeys):
                        subkey_name = winreg.EnumKey(engine_key, 0)
                        winreg.DeleteKey(engine_key, subkey_name)
                        print(f"Subkey {subkey_name} deleted.")
                except Exception as e:
                    print(f"Error deleting subkeys: {str(e)}")
                
                winreg.CloseKey(engine_key)
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, engine_key_path)
            print(f"Registry entry {engine_key_name} removed.")
        except Exception as e:
            print(f"Failed to remove registry entries: {str(e)}")


    def SetVoice(self, voice_name):
        # Setting a voice directly if it exists in the fetched voices
        for voice in self.speech_synthesizer.get_voices_list():
            if voice.short_name == voice_name:
                self.speech_synthesizer.properties[speechsdk.PropertyId.SpeechServiceConnection_SynthVoice] = voice_name
                return f"Voice set to {voice_name}"
        return "Voice not found"
    
    def SetInterest(self, event_id, enabled):
        self.event_interests[event_id] = enabled
    
    def WaitForNotifyEvent(self, timeout):
        # This would be an implementation where you monitor the audio playback and check for the next event
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.event_triggered:
                return self.event_data
            time.sleep(0.1)  # Sleep briefly to avoid high CPU usage
        return None

# Self-registration logic
if __name__ == '__main__':
    logging.debug("COM server registration starting...")
    #win32com.server.register.UseCommandLine(VoiceBroker)
    VoiceBroker = VoiceBroker(register=False)
    # unregister_sapi_entries()
