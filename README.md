Indigo Plug-Ins for InfluxDB and Kafka
---

Indigo Plug-In for writing JSON to InfluxDB

Before starting
---

* Install/license Indigo 7


Configure Indigo
---

* Download the InfluxDB Plugin directory
* Run the script install_python_modules.sh from Terminal and restart the Indigo server process.  THIS REALLY HAS TO BE DONE BEFORE INSTALLING THE PLUGIN.  Stop and restart the indigo server from the UI so it can learn about the new modules.  I hate this step, but there you go. 
* Install the plugin by double-clicking.
* Configure the hostname/user/pass/ports etc. For me the defaults for the local system are already set.
* go get a drink, turning switches on and off along the way, setting off motion sensors, opening doors, and generally being disruptive. 

Additional features added since smurfless1's original plugin
---

* Added ability to include only specific properties / states, or exclude.

For include only specific properties/states mode, you can add global properties in the plugin configuration to include for all devices.  The default value contains the most common items.  To add others on a per device basis, use the Indigo Global Property Manager and add a property called "influxIncStates".  Add fields that you want separating them with a comma.  Alternatively, add "all" and all properties will be added.

For exclude mode, it works exactly the opposite.  All device properties and states will be sent to Influx, except those that you exclude.  To exclude on a per device basis, use Indigo Global Property Manager and add a property called "influxExclStates" with a list of fields that you want, separating by a comma.  Or, use the "all" keyword.

* Added minimum update frequency option, so that devices and variables that do not get updated frequently will still get a value sent to InfluxDB occasionally
* Automatic updates


Still to do
---
* "all" not yet implemented
* Smarter validation of minimum update frequency
* Minimum update frequency for variables