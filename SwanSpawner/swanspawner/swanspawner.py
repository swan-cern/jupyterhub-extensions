<style> .nb{ font-weight:normal } </style>
<style> .nbs{ font-weight:normal; font-size:small } </style>
<style> .news{ font-weight:normal; background-color:yellow } </style>
<script type="text/javascript">
<!--

    var formConfig = {{ options_form_config }};

    var formInitialized = false;

    /**
     * Get Form data dictionary for given selectedValue.
     */
    function findFormData(form, formElement, value) {
        // Data is taken from formConfig global variable
        var formOptions = formConfig[form];
        for (key in formOptions) {
            const formData = formOptions[key];
            if (formData.type === "selection" && formData[formElement].value === value) {
                return formData;
            }
        }

        throw `${formElement} Data not found`
    }

    /**
     * Enable display of element if previously disabled, and disable if previously enabled
     */
    function toggle_visibility(id) {
        var e = document.getElementById(id);
        if(e.style.display == 'block')
            e.style.display = 'none';
        else
            e.style.display = 'block';
    }

    /**
     * Enable display of element if previously disabled, and disable if previously enabled
     */
    function validate_repository_input() {
        var repoInput = document.getElementById('repositoryOption');
        const repoPattern = new RegExp(repoInput.pattern);

        if (repoInput.value && !repoPattern.test(repoInput.value)) {
            repoInput.style.backgroundColor = '#ffcccc';
        } else {
            repoInput.style.backgroundColor = '#ffffff';
        }
    }

    /**
     * Renders a form based on config file
     */
    function adjust_form() {
        const sourceOptions = document.getElementsByName('software_source');
        let selectedSource = null;
        for (let i = 0; i < sourceOptions.length; i++) {
            if (sourceOptions[i].checked) {
                selectedSource = sourceOptions[i].value;
                break;
            }
        }

        var sourceConfig = {
            lcg: {
                optionsElement: document.getElementById("lcgReleaseOptions"),
                sourceForm: "lcg_options",
                formElement: "lcg",
            },
            customenv: {
                optionsElement: document.getElementById("builderOptions"),
                sourceForm: "customenv_options",
                formElement: "builder",
            }
        };

        // if form has not been yet initialized, initialize
        if (!formInitialized) {
            formInitialized = true;

            // set proper header for the whole form based on config
            var optionsHeader = document.getElementById('optionsHeader');
            var header = formConfig['header'];
            if (header) {
                optionsHeader.innerHTML = header;
            }

            // Loop through all source types and populate the main dropdown options (lcg -> lcg_release, customenv -> builder)
            for (var source in sourceConfig) {
                const currentSource = sourceConfig[source];
                const formOptions = formConfig[currentSource.sourceForm];
                currentSource.optionsElement.innerHTML = '';
                var firstFormOptionselected = false;

                for( var i = 0 ; i < formOptions.length ; i++ ){
                    var formEntry = formOptions[i];
                    var formOption = document.createElement("option");

                    if (formEntry.type === "label") {
                        formOption.disabled = "disabled";
                        formOption.style = "border-bottom:1px solid rgba(153,153,153,.3); margin:-10px 0 4px 0";
                        formOption.value = formEntry.label.value;
                        formOption.text = formEntry.label.text;
                    } else {
                        if (!firstFormOptionselected) {
                            firstFormOptionselected = true;
                            formOption.selected = true;
                        }
                        formOption.value = formEntry[currentSource.formElement].value;
                        formOption.text = formEntry[currentSource.formElement].text;
                    }

                    currentSource.optionsElement.add(formOption);
                }
            }
        }

        // get currently selected source and extract its configuration (formData)
        const selectedConfig = sourceConfig[selectedSource];
        var selectedValue = selectedConfig.optionsElement.value;
        var formData = findFormData(selectedConfig.sourceForm, selectedConfig.formElement, selectedValue);

        var available_configs = {
            'lcg': [
                {elementName: 'platformOptions', formKey: 'platforms'}, 
                {elementName: 'coresOptions', formKey: 'cores'}, 
                {elementName: 'memoryOptions', formKey: 'memory'}, 
                {elementName: 'clusterOptions', formKey: 'clusters'}, 
                {elementName: 'condorOptions', formKey: 'condor'}
            ],
            'customenv': [
                {elementName: 'coresOptions', formKey: 'cores'},
                {elementName: 'memoryOptions', formKey: 'memory'}
            ]
        };

        // Populate the form according to main dropdown selection
        available_configs[selectedSource].forEach(function(config) {
            var configElement = document.getElementById(config.elementName);
            configElement.innerHTML = '';

            for( var i = 0 ; i < formData[config.formKey].length ; i++ ){
                var formOption = formData[config.formKey][i];

                var selectOption = document.createElement("option");
                selectOption.value = formOption.value;
                selectOption.text = formOption.text;
                if (i === 0) {
                    selectOption.selected = true;
                }

                configElement.add(selectOption);
            }
        });

        adjust_options();
    }

    /**
     * Modifies the selection of Spark clusters and enables users to choose
     * to use the JupyterLab interface depending on the chosen platform
     */
     function adjust_options() {
        var platformOptions = document.getElementById('platformOptions');
        var clusterOptions  = document.getElementById('clusterOptions');
        var jupyterLabOption = document.getElementById("use-jupyterlab");

        /**
         * Store the chosen platform in a hidden form field, as disabled fields
         * are not sent in the request
         */ 
        var hiddenPlatformOptions = document.getElementById('hiddenPlatformOptions');

        var isAlma = platformOptions.selectedOptions[0].text.startsWith('AlmaLinux 9');
        var isNXCALS = clusterOptions.selectedOptions[0].text.startsWith('BE NXCALS (NXCals)');

        if (isAlma) {
            /* On Alma9, make sure cluster selection is enabled and that users can
            select the JupyterLab interface */
            clusterOptions.removeAttribute('disabled');
            jupyterLabOption.removeAttribute('disabled');
        } else {
            if (!isNXCALS) {
                clusterOptions.setAttribute('disabled', '');
                clusterOptions.selectedIndex = 0;
            }

            jupyterLabOption.setAttribute('disabled', '');
        }

        hiddenPlatformOptions.value = platformOptions.value;
    }

    function adjust_platforms() {
        var platformOptions = document.getElementById('platformOptions');
        var jupyterLabOption = document.getElementById('use-jupyterlab');

        if (jupyterLabOption.checked) {
            platformOptions.setAttribute('disabled', '');
        } else {
            platformOptions.removeAttribute('disabled');
        }
    }

    /**
     * Adjusts the width of the repository type dropdown element based on the selected option
     */
    function adjust_repository_dropdown() {
        const selectElement = document.getElementById('repo_type_dropdown');
        const selectedOptionText = selectElement.options[selectElement.selectedIndex].text;
        const tempElement = document.createElement('span');
        tempElement.style.visibility = 'hidden';
        tempElement.style.whiteSpace = 'nowrap';
        tempElement.style.fontSize = window.getComputedStyle(selectElement).fontSize;
        tempElement.innerHTML = selectedOptionText;

        document.body.appendChild(tempElement);
        const width = tempElement.offsetWidth;
        document.body.removeChild(tempElement);

        selectElement.style.width = `${width + 50}px`;

        const repositoryOption = document.getElementById('repositoryOption');
        if (selectElement.value === 'eos') {
            repositoryOption.placeholder = 'e.g. $CERNBOX_HOME/MyFolder';
            // Regular expression pattern for the repository provided by a EOS folder.
            repositoryOption.pattern = '^(\\\$CERNBOX_HOME(\\/[^<>\|\\\\:()&;,\n]+)*\\/?|\\/eos\\/user\\/[a-z](\\/[^<>\|\\\\:()&;,\n]+)+\\/?)$';
        } else if (selectElement.value === 'git') {
            repositoryOption.placeholder= "e.g. https://gitlab.cern.ch/user/myrepo";
            // Regular expression pattern for the repository provided by a GitLab or GitHub repository.
            repositoryOption.pattern = '^https?:\\/\\/(?:github\\.com|gitlab\\.cern\\.ch)\\/([a-zA-Z0-9_-]+)\\/([a-zA-Z0-9_-]+)\\/?$';
        }
    }

    /**
     * Modifies the displayed form according to the selected type of configuration (LCG or Custom Environments)
     */
    function toggle_form() {
        var lcgOption = document.getElementById('lcgOption');

        var customenv_config = document.getElementById('customenv_config');
        var external_res_config = document.getElementById('external_res_config');
        var lcg_config = document.getElementById('lcg_config');

        adjust_form();
        if (lcgOption.checked) {
            lcg_config.style.display = 'block';
            customenv_config.style.display = 'none';
            external_res_config.style.display = 'block';
            adjust_spark();
        } else {
            adjust_repository_dropdown();
            lcg_config.style.display = 'none';
            customenv_config.style.display = 'block';
            external_res_config.style.display = 'none';
        } 
    }

    window.onload = toggle_form;
//-->
</script>

<div>
    <label for="placeholder">
    <span class='nb' id="optionsHeader">Specify the configuration parameters for the SWAN container that will be created for you.</span>
    </label>
    <label for="alma9">
    <span class='news' id="alma9">Try out our new experimental interface based on <b>JupyterLab</b> and let us know your feedback!</span>
    </label>
    <br><br>
    <label> User Interface <a href="#" onclick="toggle_visibility('userInterfaceDetails');"><span class='nbs'>more...</span></a></label>
    <div style="display:none;" id="userInterfaceDetails">
        <span class='nb'>JupyterLab is the latest web-based interactive development environment for notebooks, code and data. More information <a target="_blank" href="https://jupyterlab.readthedocs.io/en/stable/user/interface.html">here</a>.</span>
    </div>
    <div style="display: flex; align-items: center">
        <input
          id="use-jupyterlab"
          type="checkbox"
          name="use-jupyterlab"
          value="checked"
          style="display: inline; width: initial; margin: 0 8px 0 0"
          onchange="adjust_platforms();"
        />
        <span> Try the new JupyterLab interface (experimental)</span>
    </div>
    <br>

    <!-- Source Type selection -->
    <div id="software_sourceSection">
        <h2>Software</h2>
        <label>Source <a href="#" onclick="toggle_visibility('sourceDetails');"><span class='nbs'>more...</span></a>
            <div style="display:none;" id="sourceDetails">
                <span class='nb'>Software source: curated stack (LCG) or custom environment.</span>
            </div>
        </label>
        <br>
        <input type="radio" id="lcgOption" name="software_source" value="lcg" checked onchange="toggle_form();" style="width: auto; height: auto; display: inline-block;">
        <label for="lcgOption" style="margin-right: 5%;">LCG</label>
        <input type="radio" id="customenvOption" name="software_source" value="customenv" onchange="toggle_form();" style="width: auto; height: auto; display: inline-block;">
        <label for="customenvOption">Custom Environment</label>
        <br><br>
    </div>
    
    <!-- LCG configuration -->
    <div id="lcg_config">
        <div id="lcgReleaseSection">
            <label for="lcgReleaseOptions">Software stack <a href="#" onclick="toggle_visibility('lcgReleaseDetails');"><span class='nbs'>more...</span></a>
                <div style="display:none;" id="lcgReleaseDetails">
                    <span class='nb'>The software stack to associate to the container. See the <a target="_blank" href="http://lcginfo.cern.ch/">LCG package info</a> page.</span>
                </div>
            </label>
            <select id="lcgReleaseOptions" name="LCG-rel" onchange="adjust_form();"></select>
        </div>
        <br>
        
        <div id="platformSection">
            <label for="platformOptions">Platform <a href="#" onclick="toggle_visibility('platformDetails');"><span class='nbs'>more...</span></a>
                <div style="display:none;" id="platformDetails">
                    <span class='nb'>The combination of compiler version and flags.</span>
                </div>
            </label>
            <select id="platformOptions" name="platform" onchange="adjust_options();"></select>
            <input type="hidden" id="hiddenPlatformOptions" name="platform">
        </div>
        <br>
        
        <div id="scriptenvSection">
            <label for="scriptenvOption">Environment script <a href="#" onclick="toggle_visibility('scriptenvDetails');"><span class='nbs'>more...</span></a>
                <div style="display:none;" id="scriptenvDetails">
                    <span class='nb'>User-provided bash script to define custom environment variables. The variable CERNBOX_HOME is resolved to the proper /eos/user/u/username directory.</span>
                </div>
            </label>
            <input type="text" id="scriptenvOption" name="scriptenv" placeholder="e.g. $CERNBOX_HOME/MySWAN/myscript.sh">
        </div>
        <br>
    </div>

    <!-- Custom environment configuration -->
    <div id="customenv_config" style="display: none;">
        <div id="repositorySection">
            <label for="repositoryOption">Repository 
                <a href="#" onclick="toggle_visibility('repositoryDetails');"><span class='nbs'>more...</span></a>
                <div style="display:none;" id="repositoryDetails">
                    <span class='nb'>Repository containing a requirements.txt file. It can be a path on EOS or the URL of a public git repository.</span>
                </div>
            </label>
            <br>
            <div style="display: flex;">
                <select id="repo_type_dropdown" name="repo_type" onchange="adjust_repository_dropdown();" style="width: auto; display: inline-flex; border: 1px solid #afafaf; background-color: #efefef;">
                    <option value="eos">EOS</option>
                    <option value="git">Git</option>
                </select>
                <input type="text" id="repositoryOption" name="repository" style="flex-grow: 1; margin-left: 0; border: 1px solid #afafaf;" oninput="validate_repository_input();">
            </div>
        </div>
        <br>
        
        <div id="builderSection">
            <label for="builderOptions">Builder <a href="#" onclick="toggle_visibility('builderDetails');"><span class='nbs'>more...</span></a>
                <div style="display:none;" id="builderDetails">
                    <span class='nb'>Program responsible for building the custom environment (generic or community-specific).</a></span>
                </div>
            </label>
            <select id="builderOptions" name="builder"></select>
        </div>
        <br>
    </div>
    
    <!-- Resources configuration -->
    <div id="resources_config">
        <h2>Session resources</h2>

        <div id="coresSection">
            <label for="coresOptions">Number of cores <a href="#" onclick="toggle_visibility('ncoresDetails');"><span class='nbs'>more...</span></a>
                <div style="display:none;" id="ncoresDetails">
                    <span class='nb'>Amount of cores allocated to the container.</span>
                </div>
            </label>
            <select id="coresOptions" name="ncores"></select>
        </div>
        <br>

        <div id="memorySection">
            <label for="memoryOptions">Memory <a href="#" onclick="toggle_visibility('memoryDetails');"><span class='nbs'>more...</span></a>
                <div style="display:none;" id="memoryDetails">
                    <span class='nb'>Amount of memory allocated to the container.</span>
                </div>
            </label>
            <select id="memoryOptions" name="memory"></select>
        </div>
        <br>
    </div>

    <!-- External computing resources -->
    <div id="external_res_config" style="display: block;">
        <h2>External computing resources</h2>
        
        <div id="clusterSection">
            <label for="clusterOptions">Spark cluster <a href="#" onclick="toggle_visibility('sparkClusterDetails');"><span class='nbs'>more...</span></a>
                <div style="display:none;" id="sparkClusterDetails">
                    <span class='nb'>Name of the Spark cluster to connect to from notebooks. See the <a target="_blank" href="https://hadoop-user-guide.web.cern.ch/">Hadoop User guide</a> and the <a target="_blank" href="https://sparktraining.web.cern.ch/">Spark training course</a></span>
                </div>
            </label>
            <select id="clusterOptions" name="spark-cluster"></select>
        </div>
        <br>

        <div id="condorSection">
            <label for="condorOptions">HTCondor pool <a href="#" onclick="toggle_visibility('condorDetails');"><span class='nbs'>more...</span></a>
                <div style="display:none;" id="condorDetails">
                    <span class='nb'>Name of the HTCondor pool to use.</span>
                </div>
            </label>
            <select id="condorOptions" name="condor-pool"></select>
        </div>
    </div>
</div>