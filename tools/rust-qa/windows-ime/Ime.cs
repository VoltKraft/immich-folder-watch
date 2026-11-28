using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace IfwQaIme {
    [StructLayout(LayoutKind.Sequential)]
    public struct Profile {
        public uint Type;
        public ushort Language;
        public Guid ClassId, ProfileId, Category;
        public IntPtr Substitute;
        public uint Capabilities;
        public IntPtr Layout;
        public uint Flags;
    }

    [ComImport, Guid("71c6e74d-0f28-11d8-a82a-00065b84435c"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IProfiles {
        [PreserveSig] int Clone(out IProfiles copy);
        [PreserveSig] int Next(uint count, out Profile profile, out uint fetched);
        [PreserveSig] int Reset();
        [PreserveSig] int Skip(uint count);
    }

    [ComImport, Guid("71c6e74c-0f28-11d8-a82a-00065b84435c"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IProfileManager {
        // These three SDK slots precede EnumProfiles. Only enumeration is called.
        [PreserveSig] int ActivateProfile(uint type, ushort language, ref Guid clsid, ref Guid profile, IntPtr hkl, uint flags);
        [PreserveSig] int DeactivateProfile(uint type, ushort language, ref Guid clsid, ref Guid profile, IntPtr hkl, uint flags);
        [PreserveSig] int GetProfile(uint type, ushort language, ref Guid clsid, ref Guid profile, IntPtr hkl, out Profile value);
        [PreserveSig] int EnumProfiles(ushort language, out IProfiles profiles);
    }

    public static class Native {
        [DllImport("user32.dll")] static extern int GetKeyboardLayoutList(int count, [Out] IntPtr[] layouts);
        [DllImport("user32.dll")] public static extern IntPtr GetKeyboardLayout(uint thread);
        [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
        [DllImport("user32.dll", SetLastError=true)] static extern bool PostMessageW(IntPtr hwnd, uint id, UIntPtr w, IntPtr l);
        [DllImport("imm32.dll")] public static extern bool ImmIsIME(IntPtr hkl);
        [DllImport("imm32.dll", CharSet=CharSet.Unicode)] static extern uint ImmGetDescriptionW(IntPtr hkl, StringBuilder text, uint size);
        [DllImport("user32.dll", SetLastError=true)] static extern uint SendInput(uint count, Input[] inputs, int size);

        [StructLayout(LayoutKind.Sequential)] struct Keyboard {
            public ushort virtualKey, scan;
            public uint flags, time;
            public UIntPtr extra;
        }
        [StructLayout(LayoutKind.Sequential)] struct Mouse {
            public int x, y;
            public uint data, flags, time;
            public UIntPtr extra;
        }
        [StructLayout(LayoutKind.Explicit)] struct Event {
            [FieldOffset(0)] public Keyboard keyboard;
            [FieldOffset(0)] public Mouse mouse;
        }
        [StructLayout(LayoutKind.Sequential)] struct Input { public uint type; public Event item; }

        public static Profile[] JapaneseProfiles() {
            if (Marshal.SizeOf(typeof(Profile)) != 88) throw new InvalidOperationException("Unexpected 64-bit TSF profile layout");
            Type type = Type.GetTypeFromCLSID(new Guid("33c53a50-f456-4884-b049-85fd643ecfed"), true);
            IProfileManager manager = (IProfileManager)Activator.CreateInstance(type);
            IProfiles items = null;
            try {
                // EnumProfiles(0) enumerates all system languages. Filter the returned records explicitly.
                int enumerated = manager.EnumProfiles(0, out items);
                Marshal.ThrowExceptionForHR(enumerated);
                if (enumerated == 1 && items == null) return new Profile[0];
                if (items == null) throw new InvalidOperationException("TSF returned no profile enumerator");
                var profiles = new List<Profile>();
                for (int index = 0; index < 512; index++) {
                    Profile item;
                    uint fetched;
                    int status = items.Next(1, out item, out fetched);
                    Marshal.ThrowExceptionForHR(status);
                    if (fetched == 0) return profiles.ToArray();
                    if (fetched != 1) throw new InvalidOperationException("Unexpected TSF record count");
                    if (item.Language == 0x0411) profiles.Add(item);
                    if (status == 1) return profiles.ToArray();  // S_FALSE
                }
                throw new InvalidOperationException("Unexpected TSF profile count");
            } finally {
                if (items != null) Marshal.FinalReleaseComObject(items);
                Marshal.FinalReleaseComObject(manager);
            }
        }

        public static IntPtr[] Layouts() {
            int count = GetKeyboardLayoutList(0, null);
            if (count < 1 || count > 512) throw new InvalidOperationException("Could not bound the loaded keyboard layouts");
            var items = new IntPtr[count];
            int found = GetKeyboardLayoutList(items.Length, items);
            if (found < 1 || found > count) throw new InvalidOperationException("Loaded keyboard layout list changed");
            Array.Resize(ref items, found);
            return items;
        }

        public static string Description(IntPtr hkl) {
            var text = new StringBuilder(256);
            return ImmGetDescriptionW(hkl, text, (uint)text.Capacity) > 0 ? text.ToString() : "";
        }

        public static uint OwnedThread(IntPtr hwnd, uint pid) {
            uint actual;
            uint thread = GetWindowThreadProcessId(hwnd, out actual);
            if (thread == 0 || actual != pid) throw new InvalidOperationException("Subject HWND does not belong to the child");
            return thread;
        }

        public static void RequestLayout(IntPtr hwnd, uint pid, IntPtr hkl) {
            OwnedThread(hwnd, pid);
            if (GetForegroundWindow() != hwnd || Array.IndexOf(Layouts(), hkl) < 0)
                throw new InvalidOperationException("The owned foreground HWND and a loaded layout are required");
            if (!PostMessageW(hwnd, 0x50, UIntPtr.Zero, hkl)) throw new Win32Exception(Marshal.GetLastWin32Error());
        }

        static Input Key(ushort code, bool up) {
            return new Input { type=1, item=new Event { keyboard=new Keyboard { virtualKey=code, flags=up ? 2u : 0u } } };
        }

        public static void SendFixtureKey(IntPtr hwnd, uint pid, string name) {
            OwnedThread(hwnd, pid);
            if (GetForegroundWindow() != hwnd) throw new InvalidOperationException("The subject lost foreground");
            foreach (int modifier in new[] {0x10, 0x11, 0x12, 0x5b, 0x5c}) {
                if ((GetAsyncKeyState(modifier) & 0x8000) != 0)
                    throw new InvalidOperationException("A keyboard modifier was already held");
            }
            ushort key;
            switch (name) {
                case "end": key = 0x23; break;
                case "ime-on": key = 0x16; break;
                case "a": key = 0x41; break;
                case "enter": key = 0x0d; break;
                case "backspace": key = 0x08; break;
                case "alt-backquote": key = 0xc0; break;
                default: throw new ArgumentException("Unknown fixture key");
            }
            Input[] input = name == "alt-backquote"
                ? new[] { Key(0x12,false), Key(key,false), Key(key,true), Key(0x12,true) }
                : new[] { Key(key,false), Key(key,true) };
            int size = Marshal.SizeOf(typeof(Input));
            if (size != 40) throw new InvalidOperationException("Unexpected 64-bit INPUT layout");
            uint result = SendInput((uint)input.Length, input, size);
            if (result != input.Length) {
                int error = Marshal.GetLastWin32Error();
                // Clear only depressed fixture keys while its HWND still owns foreground.
                if (result > 0 && GetForegroundWindow() == hwnd) {
                    var release = new List<Input>();
                    if (name == "alt-backquote") {
                        if (result == 2) release.Add(Key(key,true));
                        release.Add(Key(0x12,true));
                    } else release.Add(Key(key,true));
                    SendInput((uint)release.Count, release.ToArray(), size);
                }
                throw new Win32Exception(error, "SendInput did not deliver the complete fixture gesture");
            }
        }
    }
}
