async function downloadFile(action){
    var codeMirrorResultEditor = $('.CodeMirror')[1].CodeMirror;
    resultCode = codeMirrorResultEditor.getValue();

    var comparStatusCode = 0;
    var url = "/checkComparStatus";
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify ({'action': action})
      })
      .then((response) => {
        return response.json();
      })
      .then((data) => {
          if(data['success'] === 1){
             comparStatusCode = 1;
          }
          else if(data['success'] === 0){
            comparStatusCode = 0;
          }
       });

    if (resultCode && comparStatusCode && !comparIsRunning){
        var anchor=document.createElement('a');
        anchor.setAttribute('href',"/"+action);
        anchor.setAttribute('download','');
        document.body.appendChild(anchor);
        anchor.click();
        anchor.parentNode.removeChild(anchor);
    }
 }

async function terminateCompar(){
    if (comparIsRunning){
        progress = document.getElementById("progress_run");
        progress.style.background = "red";

        const response = await fetch('/terminateCompar', {
        method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify ({'jobs': Array.from(slurmJobs)})
          });
        }
 }

 function updateProgressBar (percentage) {
    progress = document.getElementById("progress_run");
    progress.style.background = "green";
    progress.style.width = percentage + "%";

    info = document.getElementById("percentage");
    info.innerHTML = percentage + "%";
 }

 function showSpeedupAndRuntime (speedup, runtime) {
    hideProgressBar();
    speedUp = document.getElementById("speed_up");
    speedUp.style.display = 'inline';
    speedUp.innerHTML = "Speedup Gained: " + speedup + ", Runtime: " + +runtime
 }

 function hideProgressBar(){
    progress_bar = document.getElementById("progress_bar");
    progress_bar.style.display = 'none';
    run_progress = document.getElementById("run_progress");
    run_progress.style.height = "0%";
    progress = document.getElementById("progress_run");
    progress.style.width =  "0%";
    info = document.getElementById("percentage");
    info.innerHTML = "0%";
 }

function resetProgressBar(){
    progress = document.getElementById("progress_run");
    progress.style.width =  "0%";
    info = document.getElementById("percentage");
    info.innerHTML = "0%";
}

async function parseLine(line){
    var job_sent_to_slurm_regex = /Job [0-9]+ sent to slurm system/;
    var job_finished_from_slurm_regex = /Job [0-9]+ status is COMPLETE/;
    var new_combination_regex = /Working on [^ \t\n]+ combination/;
    var total_combinations_regex = /[0-9]+ combinations in total/;
    var final_results_regex = /final results speedup is ([0-9]*[.])?[0-9]+ and runtime is ([0-9]*[.])?[0-9]+/;
    var found_job_sent_to_slurm = line.match(job_sent_to_slurm_regex);
    var found_job_finished_from_slurm = line.match(job_finished_from_slurm_regex);
    var found_new_combination = line.match(new_combination_regex);
    var found_total_combinations = line.match(total_combinations_regex);
    var found_final_results = line.match(final_results_regex);

    if (found_job_sent_to_slurm){
        var job_id = found_job_sent_to_slurm[0].replace(/[^0-9]/g,'');
        slurmJobs.add(job_id);
    }
    else if (found_job_finished_from_slurm){
        var job_id = found_job_finished_from_slurm[0].replace(/[^0-9]/g,'');
        slurmJobs.delete(job_id);
    }
    else if (found_new_combination){
        ranCombination += 1;
        var percentage = ((ranCombination / totalCombinationsToRun) * 100).toFixed(2);
        updateProgressBar(percentage);
    }
    else if (found_total_combinations){
        totalCombinationsToRun = found_total_combinations[0].replace(/[^0-9]/g,'');
        updateProgressBar(0);
    }
    else if (found_final_results){
        var words = found_final_results[0].split(" ");
        runtime = parseFloat(words[words.length-1]);
        speedup = parseFloat(words[4]);
        showSpeedupAndRuntime(speedup, runtime);
    }
}

