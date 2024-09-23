/*
 *  Copyright 2022 Hadrian Ward <hadrian.f.ward@gmail.com>
*/

function httpGetAsync(url, callback)// copied from stackoverflow.com/questions/247483
{
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.onreadystatechange = function() { 
        if (xmlHttp.readyState == 4){
        	if (xmlHttp.status == 200){
        		callback(xmlHttp.responseText);
        	}
        	window.waitingForServer = false;
        }
    }
    window.waitingForServer = true;
    xmlHttp.open("GET", url, true);// true for asynchronous
    xmlHttp.send(null);
}

function formatTimeDelta(seconds)
{
	dateObj = new Date(seconds * 1000);
	hours = dateObj.getUTCHours();
	minutes = dateObj.getUTCMinutes();
	seconds = dateObj.getSeconds();

	timeString = hours.toString().padStart(2, '0') + ':' +
		minutes.toString().padStart(2, '0') + ':' +
		seconds.toString().padStart(2, '0');
	return timeString;
}

function jsonDataLoaded(dataString)
{
	// deserialize data
	data = JSON.parse(dataString);
	// stuff that only needs to happen if this is the first time loading the JSON data
	if(firstTimeDataLoaded)
	{
		// insert version into DOM
		versionArray = data["server-software-version"];
		document.getElementById("version").innerHTML = versionArray.join(".");
		// get list of users and create DOM elements
		for(var name in data.clients)
		{
			document.querySelector("#players").innerHTML += "<tr><td>\"" + name + "\"</td><td><pre id=\"" + "player-status-" + name + "\"></pre></td></tr>";
		}
		// reset flag
		window.firstTimeDataLoaded = false;
	}
	// global data
	document.getElementById("global-paused").innerHTML = ["No", "Yes"][data["paused"] + 0];
	document.getElementById("global-record").innerHTML = formatTimeDelta(data["record"]);
	document.getElementById("global-time").innerHTML = formatTimeDelta(data["timer"]["t"]);
	document.getElementById("global-time-ratio").innerHTML = data["timer"]["ratio"];
	// players
	for(var name in data.clients)
	{
		var client_data = data.clients[name]
		document.querySelector("#players #player-status-" + name).innerHTML =
			"Enabled: " + client_data.general.enabled +
			"\nPaused: " + client_data.general.paused +
			"\nPosition: " + client_data.boat.pos +
			"\nAngle: " + parseInt(client_data.boat.angle) +
			"\nSpeed: " + (client_data.boat.velocity[0]**2 + client_data.boat.velocity[1]**2)**0.5 + " m/s";
	}
}

function refreshData()
{
	if(!window.waitingForServer){
		httpGetAsync("/data.json", jsonDataLoaded);
	}
}

window.firstTimeDataLoaded = true;
window.waitingForServer = false;
window.users = [];
setInterval(refreshData, 100);
