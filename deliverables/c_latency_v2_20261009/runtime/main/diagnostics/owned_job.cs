using System;
using System.IO;
using System.Diagnostics;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
namespace PldDiagnosticV2 {
    [StructLayout(LayoutKind.Sequential)] public struct IoCounters {
        public UInt64 ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public UInt64 ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }
    [StructLayout(LayoutKind.Sequential)] struct BasicLimit {
        public Int64 PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public UInt32 LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public UInt32 ActiveProcessLimit;
        public UIntPtr Affinity;
        public UInt32 PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimit {
        public BasicLimit BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct StartupInfo {
        public UInt32 cb;
        public string reserved, desktop, title;
        public UInt32 x,y,xSize,ySize,xCountChars,yCountChars,fillAttribute,flags;
        public UInt16 showWindow,reserved2;
        public IntPtr reserved2Ptr,stdInput,stdOutput,stdError;
    }
    [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {
        public IntPtr process,thread; public UInt32 processId,threadId;
    }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct ProcessEntry32 {
        public UInt32 size,usage,processId;
        public UIntPtr defaultHeapId;
        public UInt32 moduleId,threads,parentProcessId;
        public Int32 basePriority;
        public UInt32 flags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=260)] public string executable;
    }
    // The suspended launcher is assigned before any child can be created.
    // Descendants inherit this job; no breakaway permission is granted.
    public sealed class OwnedJob : IDisposable {
        IntPtr job=IntPtr.Zero, process=IntPtr.Zero;
        FileStream output,error;
        public Process Child { get; private set; }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attrs,string name);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr h,int kind,ref ExtendedLimit info,int bytes);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr h,IntPtr p);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool IsProcessInJob(IntPtr p,IntPtr h,out bool result);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr h,int kind,IntPtr info,int bytes,out int returned);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateJobObject(IntPtr h,uint code);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcess(string app,StringBuilder cmd,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref StartupInfo si,out ProcessInfo pi);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetHandleInformation(IntPtr h,uint mask,uint flags);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateFile(string file,uint access,uint share,IntPtr attrs,uint disposition,uint flags,IntPtr template);
        [DllImport("kernel32.dll", SetLastError=true)] static extern uint ResumeThread(IntPtr h);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateProcess(IntPtr h,uint code);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr h,out uint code);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr h);
        [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr CreateToolhelp32Snapshot(uint flags,uint processId);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool Process32FirstW(IntPtr snapshot,ref ProcessEntry32 entry);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool Process32NextW(IntPtr snapshot,ref ProcessEntry32 entry);
        [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GetProcessIoCounters(IntPtr p,out IoCounters counters);
        static void Check(bool ok) { if(!ok) throw new Win32Exception(Marshal.GetLastWin32Error()); }
        public OwnedJob(string python,string command,string stdout,string stderr) {
            IntPtr input=IntPtr.Zero, thread=IntPtr.Zero;
            try {
                job=CreateJobObject(IntPtr.Zero,null); Check(job!=IntPtr.Zero);
                ExtendedLimit limits=new ExtendedLimit();
                limits.BasicLimitInformation.LimitFlags=0x2000; // KILL_ON_JOB_CLOSE
                Check(SetInformationJobObject(job,9,ref limits,Marshal.SizeOf(typeof(ExtendedLimit))));
                output=new FileStream(stdout,FileMode.CreateNew,FileAccess.Write,FileShare.ReadWrite);
                error=new FileStream(stderr,FileMode.CreateNew,FileAccess.Write,FileShare.ReadWrite);
                IntPtr oh=output.SafeFileHandle.DangerousGetHandle(), eh=error.SafeFileHandle.DangerousGetHandle();
                Check(SetHandleInformation(oh,1,1)); Check(SetHandleInformation(eh,1,1));
                input=CreateFile("NUL",0x80000000,3,IntPtr.Zero,3,0,IntPtr.Zero);
                Check(input!=new IntPtr(-1)); Check(SetHandleInformation(input,1,1));
                StartupInfo si=new StartupInfo(); si.cb=(uint)Marshal.SizeOf(typeof(StartupInfo));
                si.flags=0x101; si.showWindow=0; si.stdInput=input; si.stdOutput=oh; si.stdError=eh;
                ProcessInfo pi;
                Check(CreateProcess(python,new StringBuilder(command),IntPtr.Zero,IntPtr.Zero,true,
                    0x08000004,IntPtr.Zero,null,ref si,out pi)); // NO_WINDOW | SUSPENDED
                process=pi.process; thread=pi.thread;
                Check(AssignProcessToJobObject(job,process));
                Child=Process.GetProcessById((int)pi.processId);
                IntPtr retained=Child.Handle; // retain identity before a fast target exits
                Check(ResumeThread(thread)!=0xffffffff);
            } catch {
                if(process!=IntPtr.Zero) TerminateProcess(process,125);
                Dispose(); throw;
            } finally {
                if(thread!=IntPtr.Zero) CloseHandle(thread);
                if(input!=IntPtr.Zero && input!=new IntPtr(-1)) CloseHandle(input);
                if(output!=null) SetHandleInformation(output.SafeFileHandle.DangerousGetHandle(),1,0);
                if(error!=null) SetHandleInformation(error.SafeFileHandle.DangerousGetHandle(),1,0);
            }
        }
        public bool Owns(Process p) { bool result; Check(IsProcessInJob(p.Handle,job,out result)); return result; }
        public static string ImagePath(Process p) { return p.MainModule.FileName; }
        public static int ParentPid(int processId) {
            IntPtr snapshot=CreateToolhelp32Snapshot(2,0); Check(snapshot!=new IntPtr(-1));
            try {
                ProcessEntry32 entry=new ProcessEntry32(); entry.size=(uint)Marshal.SizeOf(typeof(ProcessEntry32));
                if(!Process32FirstW(snapshot,ref entry)) Check(false);
                do { if(entry.processId==(uint)processId) return (int)entry.parentProcessId; }
                while(Process32NextW(snapshot,ref entry));
                throw new InvalidOperationException("Process is absent from the current process snapshot.");
            } finally { CloseHandle(snapshot); }
        }
        public int[] ActivePids() {
            IntPtr buffer=Marshal.AllocHGlobal(65536);
            try {
                int returned; Check(QueryInformationJobObject(job,3,buffer,65536,out returned));
                int count=Marshal.ReadInt32(buffer,4); int[] result=new int[count];
                for(int i=0;i<count;i++) result[i]=(int)Marshal.ReadIntPtr(buffer,8+i*IntPtr.Size);
                return result;
            } finally { Marshal.FreeHGlobal(buffer); }
        }
        public void Stop(uint code) { Check(TerminateJobObject(job,code)); }
        public int ExitCode() { uint code; Check(GetExitCodeProcess(process,out code)); return (int)code; }
        public void Dispose() {
            if(job!=IntPtr.Zero) { CloseHandle(job); job=IntPtr.Zero; }
            if(process!=IntPtr.Zero) { CloseHandle(process); process=IntPtr.Zero; }
            if(output!=null) { output.Dispose(); output=null; }
            if(error!=null) { error.Dispose(); error=null; }
        }
    }
}
