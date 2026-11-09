"""Capture aligned Windows CPU counters and retain partial counter statuses."""
import json, os, statistics, subprocess
from datetime import datetime, timezone
from pathlib import Path

if os.name != "nt":
    raise RuntimeError("Windows-only diagnostic")
ROOT=Path(__file__).resolve().parent.parent
RAW=ROOT/"benchmark-results/tory26-aligned-cpu-raw-v3.json"
SUMMARY=ROOT/"benchmark-results/tory26-aligned-cpu-summary-v3.json"
PS=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

def parse_capture(capture):
    n=capture["logical_processors"]
    process_rows=[]; systems=[]; active={}; generations={}
    total_names={"% processor time","% user time","% privileged time","% interrupt time","% dpc time"}
    for i,sample in enumerate(capture["samples"]):
        proc={}; system={}
        for c in sample.get("counters",[]):
            path=c.get("path","").lower(); name=path.rsplit("\\",1)[-1]
            if "\\processor(_total)\\" in path: system[name]=c
            elif "\\process(" in path: proc.setdefault(c.get("instance",""),{})[name]=c
        systems.append({"sample":i,"timestamp":sample.get("timestamp"),"counters":system})
        current={}
        for instance,values in proc.items():
            idc=values.get("id process"); elapsedc=values.get("elapsed time"); cpuc=values.get("% processor time")
            valid_id=idc is not None and idc.get("status")==0
            valid_cpu=cpuc is not None and cpuc.get("status")==0
            pid=int(idc["value"]) if valid_id else None
            elapsed=elapsedc.get("value") if elapsedc and elapsedc.get("status")==0 else None
            key=(instance,pid) if pid is not None else None
            gen=None
            if key:
                prev=active.get(key)
                if prev is None or (elapsed is not None and prev is not None and prev["elapsed"] is not None and elapsed < prev["elapsed"]):
                    generations[key]=generations.get(key,0)+1
                gen=generations[key]; current[key]={"elapsed":elapsed,"generation":gen}
            process_rows.append({"sample":i,"timestamp":sample.get("timestamp"),"instance":instance,"pid":pid,"elapsed_seconds":elapsed,"generation":gen,"valid":valid_id and valid_cpu,"cpu_status":cpuc.get("status") if cpuc else None,"pid_status":idc.get("status") if idc else None,"raw_process_cpu_percent":cpuc.get("value") if valid_cpu else None,"normalized_machine_cpu_percent":cpuc.get("value")/n if valid_cpu else None})
        active=current
    complete=[]; gaps=[]
    for i,s in enumerate(systems):
        # An interval is incomplete if any returned process record lacks a valid PID or CPU value.
        rows=[r for r in process_rows if r["sample"]==i]
        ok=bool(rows) and all(r["valid"] for r in rows) and all(s["counters"].get(k,{}).get("status")==0 for k in total_names)
        s["complete_interval"]=ok
        if ok:
            psum=sum(r["normalized_machine_cpu_percent"] for r in rows)
            s["normalized_process_sum_percent"]=psum
            gaps.append(s["counters"]["% processor time"]["value"]-psum)
            complete.append(psum)
        else: s["normalized_process_sum_percent"]=None
    med=lambda vals: statistics.median(vals) if vals else None
    summary={"recorded_at_utc":datetime.now(timezone.utc).isoformat(),"duration_seconds":60,"sample_interval_seconds":1,"sample_count":len(systems),"logical_processors":n,"system_valid_counts":{k:sum(1 for s in systems if s["counters"].get(k,{}).get("status")==0) for k in sorted(total_names)},"system_medians_percent":{k:med([s["counters"][k]["value"] for s in systems if s["counters"].get(k,{}).get("status")==0]) for k in sorted(total_names)},"complete_process_interval_count":len(complete),"process_interval_count":len(systems),"normalized_process_sum_median_percent":med(complete),"median_accounting_gap_percentage_points_complete_intervals_only":med(gaps),"process_observation_count":len(process_rows),"invalid_process_observation_count":sum(not r["valid"] for r in process_rows),"distinct_instance_pid_generations":len({(r["instance"],r["pid"],r["generation"]) for r in process_rows if r["generation"] is not None}),"limitations":["Processes that start and exit entirely between one-second samples may not appear.","Instance, PID and elapsed time track observed process replacement and PID reuse.","No process aggregate or CPU gap is calculated for incomplete intervals."]}
    return {"systems":systems,"processes":process_rows,"summary":summary}

def main():
    if RAW.exists() or SUMMARY.exists(): raise RuntimeError("Refusing to overwrite CPU evidence")
    ps=r'''$ErrorActionPreference='Continue'; $n=[Environment]::ProcessorCount
$paths=@('\Processor(_Total)\% Processor Time','\Processor(_Total)\% User Time','\Processor(_Total)\% Privileged Time','\Processor(_Total)\% Interrupt Time','\Processor(_Total)\% DPC Time','\Process(*)\% Processor Time','\Process(*)\ID Process','\Process(*)\Elapsed Time')
$sets=@(Get-Counter -Counter $paths -SampleInterval 1 -MaxSamples 60 -ErrorAction SilentlyContinue); $out=@()
foreach($set in $sets){$rows=@(); foreach($c in $set.CounterSamples){$rows += [pscustomobject]@{path=$c.Path;instance=$c.InstanceName;status=[int]$c.Status;value=[double]$c.CookedValue}}; $out += [pscustomobject]@{timestamp=$set.Timestamp.ToUniversalTime().ToString('o');counters=$rows}}
[pscustomobject]@{logical_processors=$n;sample_interval_seconds=1;requested_samples=60;samples=$out}|ConvertTo-Json -Depth 6 -Compress'''
    result=subprocess.run([PS,"-NoProfile","-NonInteractive","-Command",ps],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if not result.stdout.strip(): raise RuntimeError("Get-Counter returned no capture; stderr="+result.stderr[-4000:])
    capture=json.loads(result.stdout); parsed=parse_capture(capture)
    with RAW.open("x",encoding="utf-8") as f: json.dump({"method":"Get-Counter aligned 1-second samples, 60 requested; raw paths/status/value preserved",**capture,"parsed_system_samples":parsed["systems"],"parsed_process_samples":parsed["processes"]},f,indent=2); f.write("\n")
    with SUMMARY.open("x",encoding="utf-8") as f: json.dump(parsed["summary"],f,indent=2); f.write("\n")
    print(json.dumps({"raw":str(RAW),"summary":str(SUMMARY),**parsed["summary"],"powershell_exit_code":result.returncode},indent=2))

if __name__=="__main__": main()
