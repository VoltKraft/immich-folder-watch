namespace IfwQaReader {
    using System;
    using System.ComponentModel;
    using System.Runtime.InteropServices;

    public static class Keyboard {
        // Native INPUT for both supported 64-bit ABIs. The largest union member is MOUSEINPUT.
        [StructLayout(LayoutKind.Explicit, Size=40)] struct Input {
            [FieldOffset(0)] public uint type;
            [FieldOffset(10)] public ushort scan;
            [FieldOffset(12)] public uint flags;
        }
        [StructLayout(LayoutKind.Sequential)] struct ThreadInfo {
            public uint size, flags;
            public IntPtr active, focus, capture, menu, move, caret;
            public int left, top, right, bottom;
        }
        [DllImport("user32.dll")] static extern bool GetGUIThreadInfo(uint thread, ref ThreadInfo info);
        [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr window, uint flag);
        [DllImport("user32.dll")] static extern IntPtr GetKeyboardLayout(uint thread);
        [DllImport("user32.dll")] static extern uint MapVirtualKeyExW(uint code, uint mapType, IntPtr layout);
        [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint count, Input[] inputs, int size);

        public static IntPtr Focus(IntPtr window, uint pid) {
            uint owner;
            uint thread = IfwObservedWindow.GetWindowThreadProcessId(window, out owner);
            var info = new ThreadInfo { size=(uint)Marshal.SizeOf(typeof(ThreadInfo)) };
            if (thread == 0 || owner != pid || !IfwObservedWindow.OnInputDesktop() ||
                    IfwObservedWindow.GetForegroundWindow() != window || !GetGUIThreadInfo(thread, ref info) ||
                    info.active != window || info.focus == IntPtr.Zero || GetAncestor(info.focus, 2) != window ||
                    IfwObservedWindow.GetWindowThreadProcessId(info.focus, out owner) != thread || owner != pid)
                throw new InvalidOperationException("The subject does not own native keyboard focus on the input desktop.");
            return info.focus;
        }

        static Input Stroke(ushort code, bool extended, bool up) {
            return new Input { type=1, scan=code, flags=8u | (extended ? 1u : 0u) | (up ? 2u : 0u) };
        }
        public static int Press(IntPtr window, uint pid, string gesture) {
            // E0 53 is the dedicated Delete key. Map shortcut letters through the subject's layout.
            ushort modifier=0, key=0, letter=0;
            bool extendedModifier=false, extendedKey=false;
            switch (gesture) {
                case "SelectAll": modifier=0x1d; letter=0x41; break;
                case "Copy": modifier=0x1d; letter=0x43; break;
                case "Paste": modifier=0x1d; letter=0x56; break;
                case "Delete": key=0x53; extendedKey=true; break;
                case "PassNextKey": modifier=0x52; extendedModifier=true; key=0x3c; break;
                default: throw new ArgumentException("Unexpected reader gesture.");
            }
            if (letter!=0) {
                uint owner;
                uint thread=IfwObservedWindow.GetWindowThreadProcessId(window,out owner);
                if (thread==0 || owner!=pid) throw new InvalidOperationException("The target keyboard layout is unavailable.");
                uint scan=MapVirtualKeyExW(letter,4,GetKeyboardLayout(thread));
                if (scan==0 || scan>0xff) throw new InvalidOperationException("Cannot map the shortcut letter to a scan code.");
                key=(ushort)scan;
            }
            var down=Stroke(key,extendedKey,false);
            var up=Stroke(key,extendedKey,true);
            var release=Stroke(modifier,extendedModifier,true);
            var events = modifier==0 ? new[] {down,up} : new[] {Stroke(modifier,extendedModifier,false),down,up,release};
            Focus(window,pid);
            if (IntPtr.Size!=8) throw new PlatformNotSupportedException("Expected a 64-bit Windows input observer.");
            int size=Marshal.SizeOf(typeof(Input));
            uint sent=SendInput((uint)events.Length,events,size);
            if (sent==events.Length) return events.Length;
            int error=Marshal.GetLastWin32Error();
            if (sent>0) {
                Focus(window,pid);
                if (modifier==0 || sent==2) SendInput(1,new[]{up},size);
                if (modifier!=0) SendInput(1,new[]{release},size);
            }
            throw new Win32Exception(error,"Incomplete native reader gesture.");
        }
    }
}
