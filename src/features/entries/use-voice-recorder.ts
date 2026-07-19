'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export const MAX_RECORDING_SECONDS = 20 * 60;

export type VoiceRecorderState =
  | 'idle'
  | 'requesting'
  | 'recording'
  | 'paused'
  | 'ready'
  | 'permission-denied'
  | 'failed';

export function useVoiceRecorder() {
  const [state, setState] = useState<VoiceRecorderState>('idle');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [recording, setRecording] = useState<Blob>();
  const recorderRef = useRef<MediaRecorder | undefined>(undefined);
  const streamRef = useRef<MediaStream | undefined>(undefined);
  const chunksRef = useRef<Blob[]>([]);

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = undefined;
  }, []);

  const stop = useCallback(() => {
    if (!recorderRef.current || recorderRef.current.state === 'inactive')
      return;
    recorderRef.current.stop();
  }, []);

  useEffect(() => {
    if (state !== 'recording') return;
    const interval = window.setInterval(
      () => setElapsedSeconds((current) => current + 1),
      1000,
    );
    return () => window.clearInterval(interval);
  }, [state]);

  useEffect(() => {
    if (elapsedSeconds >= MAX_RECORDING_SECONDS) stop();
  }, [elapsedSeconds, stop]);

  useEffect(() => releaseStream, [releaseStream]);

  async function start() {
    setState('requesting');
    setElapsedSeconds(0);
    setRecording(undefined);
    chunksRef.current = [];

    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error('Voice recording is not available in this browser.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      streamRef.current = stream;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        if (recorderRef.current === recorder) recorderRef.current = undefined;
        releaseStream();
        setState('failed');
      };
      recorder.onstop = () => {
        if (recorderRef.current !== recorder) return;
        const nextRecording = new Blob(chunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        });
        recorderRef.current = undefined;
        releaseStream();
        setRecording(nextRecording);
        setState(nextRecording.size > 0 ? 'ready' : 'failed');
      };
      recorder.start();
      setState('recording');
    } catch (error) {
      releaseStream();
      setState(
        error instanceof DOMException && error.name === 'NotAllowedError'
          ? 'permission-denied'
          : 'failed',
      );
    }
  }

  function pause() {
    if (recorderRef.current?.state !== 'recording') return;
    recorderRef.current.pause();
    setState('paused');
  }

  function resume() {
    if (recorderRef.current?.state !== 'paused') return;
    recorderRef.current.resume();
    setState('recording');
  }

  function reset() {
    const recorder = recorderRef.current;
    recorderRef.current = undefined;
    if (recorder && recorder.state !== 'inactive') {
      recorder.ondataavailable = null;
      recorder.onerror = null;
      recorder.onstop = null;
      recorder.stop();
    }
    releaseStream();
    chunksRef.current = [];
    setRecording(undefined);
    setElapsedSeconds(0);
    setState('idle');
  }

  return {
    elapsedSeconds,
    pause,
    recording,
    reset,
    resume,
    start,
    state,
    stop,
  };
}
