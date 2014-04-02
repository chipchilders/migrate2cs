<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <meta http-equiv="content-type" content="text/html; charset=utf-8"/>
    <title>migrate2cs</title>
    <link rel="stylesheet" type="text/css" href="/static/views/plugins/jquery-ui-1.10.4.custom/css/migrate-ui/jquery-ui-1.10.4.custom.css">
    <link rel="stylesheet" type="text/css" href="/static/views/css/style.css">
    <script type="text/javascript" src="/static/views/js/json2.js"></script>
    <script type="text/javascript" src="/static/views/plugins/jquery-ui-1.10.4.custom/js/jquery-1.10.2.js"></script>
    <script type="text/javascript" src="/static/views/plugins/jquery-ui-1.10.4.custom/js/jquery-ui-1.10.4.custom.min.js"></script>
    <script type="text/javascript">
      var cs_objs = {{!cs_objs}};
      var vms = {{!vms}};
      var vm_order = {{!vm_order}};

      $(function() {
        $('#accordion').accordion({
          heightStyle: 'content',
          disabled: true,
          animate: false
        });
        $('button').button();
        //$('.discover').on('click', function() {
        //  $('#accordion').accordion('option', 'active', 1);
        //});
        //$('.edit_config').on('click', function() {
        //  $('#accordion').accordion('option', 'active', 0);
        //});

        $('.action_collapse').on('click', function() {
          $('.vm_list .vm_content').hide();
        });
        $('.action_expand').on('click', function() {
          $('.vm_list .vm_content').show();
        });
        $('.vm_list h4').on('click', function() {
          if ($(this).siblings('.vm_content').is(':visible')) {
            $(this).siblings('.vm_content').hide();
          } else {
            $(this).siblings('.vm_content').show();
          }
        });

        $('.action_select').on('click', function() {
          $('.vm_list .vm_select input').prop('checked', true);
        });
        $('.action_unselect').on('click', function() {
          $('.vm_list .vm_select input').prop('checked', false);
        });


        // accounts
        option_html = '<option value="">Select</option>';
        for (var id in cs_objs['accounts']) {
          option_html += '<option value="'+id+'">'+cs_objs['accounts'][id]['display']+'</option>';
        }
        $('#dst_account').html(option_html);
        if ($('#dst_account option').size() == 2) {
          $($('#dst_account').children()[1]).prop('selected', true);
        }

        // handle changes to the select boxes (namely zone -> network)
        $('#dst_account').on('change', get_account_resources);
        $('#dst_account').trigger('change');

        // handle when a config is applied to a selection of VMs
        $('.action_apply').on('click', apply_config_to_vms);


        // check that the selected VMs are ready and move on to the migration
        $('.migrate').on('click', function() {
          var ready = true;
          var vms = {};
          $('.vm_select .checkbox:checked').each(function() {
            var vm = $(this).closest('.vm');
            if ($(vm).find('.dst_account_id').text() != '' && $(vm).find('.dst_zone_id').text() !='' &&
                $(vm).find('.dst_compute_offering_id').text() != '') {
              var vm_obj = {};
              var cs_obj = cs_objs['accounts'][$(vm).find('.dst_account_id').text()];
              vm_obj['cs_account'] = cs_obj['account'];
              vm_obj['cs_domain'] = cs_obj['domain'];
              vm_obj['cs_zone'] = $(vm).find('.dst_zone_id').text();
              vm_obj['cs_service_offering'] = $(vm).find('.dst_compute_offering_id').text();
              if ($(vm).find('.dst_network_id').text() != '') {
                vm_obj['cs_network'] = $(vm).find('.dst_network_id').text();
              }
              vms[$(vm).data('id')] = vm_obj;
            } else {
              ready = false;
              alert($(vm).find('h4').text()+" is missing required fields for migration.");
            }
          });
          console.log(vms);
          if (ready) {
            $('#accordion').accordion('option', 'active', 1);
          }
        });

      }); // end onload

      
      // FUNCTIONS //

      // onchange of the account, go and fetch the resources that account has access to
      function get_account_resources(event) {
        var display = $('#dst_account').val();
        $('#dst_account').siblings('select').prop('disabled', true).find('option').remove();
        if (display != '') {
          $.ajax({
            url: "/discover/account",
            type: "POST",
            data: {
              "account":JSON.stringify(cs_objs['accounts'][display])
            },
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            beforeSend: function(xhr, settings) {
              $('#dst_account').siblings('.account_loader').show();
            },
            success: function(data) {
              cs_objs = data;
              update_account_resources();
            },
            failure: function(err) {
              alert(err);
            },
            complete: function(xhr, status) {
              $('#dst_account').siblings('.account_loader').hide();
            }
          });
        }
      }

      // once we have the resources for a specific account, update the dropdowns to reflect the resources
      function update_account_resources() {
        $('#dst_account').siblings('select').prop('disabled', false);
        var display = $('#dst_account').val();
        // zones
        option_html = '<option value="">Select</option>';
        for (var id in cs_objs['accounts'][display]['zones']) {
          option_html += '<option value="'+id+'">'+cs_objs['accounts'][display]['zones'][id]['display']+'</option>';
        }
        $('#dst_zone').html(option_html);
        if ($('#dst_zone option').size() == 2) {
          $($('#dst_zone').children()[1]).prop('selected', true);
        }

        // networks
        option_html = '<option value="">Select</option>';
        for (var id in cs_objs['accounts'][display]['networks']) {
          option_html += '<option value="'+id+'">'+cs_objs['accounts'][display]['networks'][id]['display']+'</option>';
        }
        $('#dst_network').html(option_html);
        if ($('#dst_network option').size() == 2) {
          $($('#dst_network').children()[1]).prop('selected', true);
        }

        // offerings
        option_html = '<option value="">Select</option>';
        for (var id in cs_objs['accounts'][display]['offerings']) {
          option_html += '<option value="'+id+'">'+cs_objs['accounts'][display]['offerings'][id]['display']+'</option>';
        }
        $('#dst_compute_offering').html(option_html);
        if ($('#dst_compute_offering option').size() == 2) {
          $($('#dst_compute_offering').children()[1]).prop('selected', true);
        }

        // handle changes to the select boxes (namely zone -> network)
        $('#dst_zone').on('change', function() {
          var zone_id = $(this).val();
          if (zone_id != '') {
            if (cs_objs['accounts'][display]['zones'][zone_id]['network'] == 'basic') { // basic network
              $('#dst_network').prop('disabled', true);
            } else { // advanced network
              $('#dst_network').prop('disabled', false);
              $('#dst_network').children().each(function(index) {
                var net_id = $(this).val();
                if (net_id != '') {
                  if (cs_objs['accounts'][display]['networks'][net_id]['zone'] == zone_id) {
                    $(this).prop('disabled', false);
                  } else {
                    $(this).prop('disabled', true);
                  }
                }
              });
            }
          } else {
            $('#dst_network').prop('disabled', false);
          }
        });
        $('#dst_zone').trigger('change');
      }

      // clicking the apply button to apply a config to the selected VMs
      function apply_config_to_vms() {
        if ($('#dst_account option:selected').val() != '' && $('#dst_zone option:selected').val() != '' &&
            $('#dst_compute_offering option:selected').val() != '') {
          $('.vm_select .checkbox:checked').each(function() {
            var vm = $(this).closest('.vm');
            $(vm).find('.dst_account').text($('#dst_account option:selected').text());
            $(vm).find('.dst_account_id').text($('#dst_account option:selected').val());
            $(vm).find('.dst_zone').text($('#dst_zone option:selected').text());
            $(vm).find('.dst_zone_id').text($('#dst_zone option:selected').val());
            $(vm).find('.dst_compute_offering').text($('#dst_compute_offering option:selected').text());
            $(vm).find('.dst_compute_offering_id').text($('#dst_compute_offering option:selected').val());
            if (!$('#dst_network').is(':disabled') && $('#dst_network option:selected').val() != '') {
              $(vm).find('.dst_network').text($('#dst_network option:selected').text());
              $(vm).find('.dst_network_id').text($('#dst_network option:selected').val());
            } else {
              $(vm).find('.dst_network').text('Use Default');
              $(vm).find('.dst_network_id').text('');
            }
          });
        } else {
          alert('Please select a configuration for all the requred fields.');
        }
      }
    </script>
	</head>
	<body>
    <div id="wrapper">
      <h1>Migrate to CloudPlatform</h1>
      <div id="accordion">
        <!--<h3>Define the Configuration</h3>
        <div class="section">
          <div class="left">
            <h4>VMWare Details</h4>
            <label for="src_ip">Server IP</label> <input type="text" id="src_ip" /><br />
            <label for="src_user">Username</label> <input type="text" id="src_user" /><br />
            <label for="src_pass">Password</label> <input type="text" id="src_pass" />
          </div>
          <div class="right">
            <h4>CloudPlatform Details</h4>
            <label for="cs_ip">CloudPlatform IP</label> <input type="text" id="cs_ip" /><br />
            <label for="cs_api_key">API Key</label> <input type="text" id="cs_api_key" /><br />
            <label for="cs_secret_key">Secret Key</label> <input type="text" id="cs_secret_key" />
          </div>
          <div class="clear button_wrapper">
            <button class="discover">Connect and Discover</button>
          </div>
        </div>-->

        <h3>Select and Migrate VMs</h3>
        <div class="section">
          <!--<button class="edit_config">Edit Configuration</button>-->
          <div class="action_panel">
            <h4>Associate CloudPlatform settings to the selected VMs</h4>
            <div class="left">
              <label>Account*</label>
              <select id="dst_account" class="dst_account"></select>
                <span class="account_loader" style="display:none;"><img src="/static/views/images/ajax-loader.gif" /></span><br />
              <label>Zone*</label>
              <select id="dst_zone" class="dst_zone"></select><br />
              <label>Network&nbsp;</label>
              <select id="dst_network" class="dst_network"></select><br />
              <label>Compute Offering*</label>
              <select id="dst_compute_offering" class="dst_compute_offering"></select>
            </div>
            
            <div class="right">
              <div class="action_row">
                <button class="action_collapse">Collapse VMs</button> <button class="action_select">Select All VMs</button>
                <div class="clear"> </div>
              </div>
              <div class="action_row">
                <button class="action_expand">Expand VMs</button> <button class="action_unselect">Unselect All VMs</button>
                <div class="clear"> </div>
              </div>
              <button class="action_apply">Apply to Selected VMs</button>
            </div>
            <div class="clear"> </div>
          </div>
          <div class="vm_list">
            <div class="vm" data-id="1" >
              <h4>CentOS</h4>
              <span class="vm_select">
                <span class="vm_select_label">Select</span>
                <input id="1" class="checkbox" type="checkbox" /><label class="checkbox_label" for="1"></label>
              </span>
              <div class="vm_content">
                <div class="left">
                  <div class="detail"><span class="label">Root Drive</span> CentOS65.ovf</div>
                  <div class="detail"><span class="label">Data Drive</span> Expanded.ovf</div>
                  <div class="detail"><span class="label">Memory</span> 1024 Mb</div>
                  <div class="detail"><span class="label">CPU</span> 2 x 1000 Mhz</div>
                </div>
                <div class="right">
                  <div class="detail">
                    <span class="label">Account</span>
                    <span class="dst_account"> - - - </span>
                    <span class="dst_account_id hidden"></span>
                  </div>
                  <div class="detail">
                    <span class="label">Zone</span>
                    <span class="dst_zone"> - - - </span>
                    <span class="dst_zone_id hidden"></span>
                  </div>
                  <div class="detail">
                    <span class="label">Network</span>
                    <span class="dst_network"> - - - </span>
                    <span class="dst_network_id hidden"></span>
                  </div>
                  <div class="detail">
                    <span class="label">Compute Offering</span>
                    <span class="dst_compute_offering"> - - - </span>
                    <span class="dst_compute_offering_id hidden"></span>
                  </div>
                </div>
                <div class="clear"></div>
              </div>
            </div>

            <div class="vm" data-id="2">
              <h4>Windows 2008 Enterprise</h4>
              <span class="vm_select">
                <span class="vm_select_label">Select</span>
                <input id="2" class="checkbox" type="checkbox" /><label class="checkbox_label" for="2"></label>
              </span>
              <div class="vm_content">
                <div class="left">
                  <div class="detail"><span class="label">Root Drive</span> Windows-2008-Ent.ovf</div>
                  <div class="detail"><span class="label">Data Drive</span> 5GbDrive.ovf</div>
                  <div class="detail"><span class="label">Memory</span> 2048 Mb</div>
                  <div class="detail"><span class="label">CPU</span> 4 x 1000 Mhz</div>
                </div>
                <div class="right">
                  <div class="detail">
                    <span class="label">Account</span>
                    <span class="dst_account"> - - - </span>
                    <span class="dst_account_id hidden"></span>
                  </div>
                  <div class="detail">
                    <span class="label">Zone</span>
                    <span class="dst_zone"> - - - </span>
                    <span class="dst_zone_id hidden"></span>
                  </div>
                  <div class="detail">
                    <span class="label">Network</span>
                    <span class="dst_network"> - - - </span>
                    <span class="dst_network_id hidden"></span>
                  </div>
                  <div class="detail">
                    <span class="label">Compute Offering</span>
                    <span class="dst_compute_offering"> - - - </span>
                    <span class="dst_compute_offering_id hidden"></span>
                  </div>
                </div>
                <div class="clear"></div>
              </div>
            </div>

          </div>
          <div class="clear button_wrapper">
            <button class="migrate">Migrate Selected VMs</button>
          </div>
        </div>

        <h3>Migration Progress</h3>
        <div class="section">
          <textarea class="log_output"></textarea>
          <div class="clear button_wrapper">
            <button class="download_log">Download Full Log</button>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
            