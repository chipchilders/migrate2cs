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
      var poll_interval = null;

      $(function() {
        $('#accordion').accordion({
          heightStyle: 'content',
          /*disabled: true,*/
          animate: false
        });
        $('button').button();
        //$('.discover').on('click', function() {
        //  $('#accordion').accordion('option', 'active', 1);
        //});
        //$('.edit_config').on('click', function() {
        //  $('#accordion').accordion('option', 'active', 0);
        //});

        // expand and collapse functionality
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

        // select all and select none functionality
        $('.action_select').on('click', function() {
          $('.vm_list .vm_select input').prop('checked', true);
        });
        $('.action_unselect').on('click', function() {
          $('.vm_list .vm_select input').prop('checked', false);
        });

        // build the VM list
        build_vm_list();

        // accounts
        option_html = '<option value="">Select</option>';
        for (var id in cs_objs['accounts']) {
          option_html += '<option value="'+id+'">'+cs_objs['accounts'][id]['display']+'</option>';
        }
        $('#dst_account').html(option_html);
        if ($('#dst_account option').size() == 2) {
          $($('#dst_account').children()[1]).prop('selected', true);
        }

        // handle changes to the account select box
        $('#dst_account').on('change', get_account_resources);
        $('#dst_account').trigger('change');

        // handle when a config is applied to a selection of VMs
        $('.action_apply').on('click', apply_config_to_vms);

        // check that the selected VMs are ready and move on to the migration
        $('.migrate').on('click', migrate_selected_vms);
        // re-open the 'select and migrate' section
        //$('.edit_migration').on('click', function() {
        //  $('#accordion').accordion('option', 'active', 0);
        //});

      }); // end onload

      
      // FUNCTIONS //

      // build the VM list (and populate it with previous details if any)
      function build_vm_list() {
        for (var i=0; i<vm_order.length; i++) {
          var vm_id = vm_order[i];
          var vm_obj = vms[vm_id];
          var vm_el = $('#vm_tpl').clone(true);
          $(vm_el).removeAttr('id'); // get rid of the 'vm_tpl' id
          $(vm_el).data('id', vm_id);
          $(vm_el).find('h4').text(vm_obj['src_name']);
          $(vm_el).find('.vm_select .checkbox').attr('id', vm_id);
          $(vm_el).find('.vm_select .checkbox_label').attr('for', vm_id);

          if (vm_obj['state'] != '') {
            $(vm_el)
              .removeClass('exported')
              .removeClass('imported')
              .removeClass('launched')
              .removeClass('migrated')
              .addClass(vm_obj['state']);
              $(vm_el).find('.vm_state').text(vm_obj['state']);
          }
          
          // build vm details
          var details = '';
          //details += '<div class="detail"><span class="label">Path</span> <span class="value">'+vm_obj['src_path']+'</span></div>';
          details += '<div class="detail"><span class="label">Type</span> <span class="value">'+vm_obj['src_type']+'</span></div>';
          details += '<div class="detail"><span class="label">Memory</span> <span class="value">'+vm_obj['src_memory']+'Mb</span></div>';
          details += '<div class="detail"><span class="label">CPUs</span> <span class="value">'+vm_obj['src_cpus']+'</span></div>';
          details += '<div class="detail"><span class="label">Root Disk</span> <span class="value">'+vm_obj['src_disks'][0]['label']+' ('+(vm_obj['src_disks'][0]['size']/(1024*1024)).toFixed(1)+' GB)</span></div>';
          for (var d=1; d<vm_obj['src_disks'].length; d++) {
            details += '<div class="detail"><span class="label">Data Disk</span> <span class="value">'+vm_obj['src_disks'][d]['label']+' ('+(vm_obj['src_disks'][d]['size']/(1024*1024)).toFixed(1)+' GB)</span></div>';
          }
          $(vm_el).find('.vm_content .left').html(details);

          // check if there are CS details for this vm and populate if so.
          if ('cs_account_display' in vm_obj) {
            $(vm_el).find('.dst_account').text(vm_obj['cs_account_display']);
            $(vm_el).find('.dst_account_id').text(vm_obj['cs_account_display']);
          }
          if ('cs_zone' in vm_obj) {
            $(vm_el).find('.dst_zone').text(vm_obj['cs_zone_display']);
            $(vm_el).find('.dst_zone_id').text(vm_obj['cs_zone']);
          }
          if ('cs_service_offering' in vm_obj) {
            $(vm_el).find('.dst_compute_offering').text(vm_obj['cs_service_offering_display']);
            $(vm_el).find('.dst_compute_offering_id').text(vm_obj['cs_service_offering']);
          }
          if ('cs_network' in vm_obj) {
            $(vm_el).find('.dst_network').text(vm_obj['cs_network_display']);
            $(vm_el).find('.dst_network_id').text(vm_obj['cs_network']);
          }

          // append the vm element
          $('.vm_list').append(vm_el);
        }
      }

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
            error: function(xhr, status, err) {
              $('#notice').removeClass().addClass('error').html('Failed to discover the CloudPlatform accounts...<br />'+status+': '+err);
              $('#notice').show();
              setTimeout(function() {
                $('#notice').fadeOut();
              }, 5000);
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
          if ($('.vm_select .checkbox:checked').length > 0) {
            $('.vm_select .checkbox:checked').each(function() {
              var vm = $(this).closest('.vm');
              var vm_id = $(vm).data('id');
              $(vm).find('.dst_account').text($('#dst_account option:selected').text());
              $(vm).find('.dst_account_id').text($('#dst_account option:selected').val());
              vms[vm_id]['cs_account_display'] = $('#dst_account option:selected').val();
              $(vm).find('.dst_zone').text($('#dst_zone option:selected').text());
              $(vm).find('.dst_zone_id').text($('#dst_zone option:selected').val());
              vms[vm_id]['cs_zone_display'] = $('#dst_zone option:selected').text();
              vms[vm_id]['cs_zone'] = $('#dst_zone option:selected').val();
              $(vm).find('.dst_compute_offering').text($('#dst_compute_offering option:selected').text());
              $(vm).find('.dst_compute_offering_id').text($('#dst_compute_offering option:selected').val());
              vms[vm_id]['cs_service_offering_display'] = $('#dst_compute_offering option:selected').text();
              vms[vm_id]['cs_service_offering'] = $('#dst_compute_offering option:selected').val();
              if (!$('#dst_network').is(':disabled') && $('#dst_network option:selected').val() != '') {
                $(vm).find('.dst_network').text($('#dst_network option:selected').text());
                $(vm).find('.dst_network_id').text($('#dst_network option:selected').val());
                vms[vm_id]['cs_network_display'] = $('#dst_network option:selected').text();
                vms[vm_id]['cs_network'] = $('#dst_network option:selected').val();
              } else {
                $(vm).find('.dst_network').text('Use Default');
                $(vm).find('.dst_network_id').text('');
              }
            });
            // the vms object has been updated.  save the updated vms object to the server.
            $.ajax({
              url: "/vms/save",
              type: "POST",
              data: {
                "vms":JSON.stringify(vms)
              },
              contentType: "application/json; charset=utf-8",
              success: function(data) {
                $('#notice').removeClass().html('The applied configuration was saved to the server...');
                $('#notice').show();
                setTimeout(function() {
                  $('#notice').fadeOut();
                }, 5000);
              },
              error: function(xhr, status, err) {
                $('#notice').removeClass().addClass('error').html('Failed to save the configuration to the server...<br />'+status+': '+err);
                $('#notice').show();
                setTimeout(function() {
                  $('#notice').fadeOut();
                }, 5000);
              }
            });
          } else {
            $('#notice').removeClass().addClass('error').html('You need to select VMs to apply the configuration to...');
            $('#notice').show();
            setTimeout(function() {
              $('#notice').fadeOut();
            }, 5000);
          }
        } else {
          $('#notice').removeClass().addClass('error').html('Please select a configuration for all the requred fields...');
          $('#notice').show();
          setTimeout(function() {
            $('#notice').fadeOut();
          }, 5000);
        }
      }

      // validate and migrate selected VMs
      function migrate_selected_vms() {
        $('.migrate').attr('disabled','disabled');
        var ready = true;
        var migrate = [];
        $('#notice').html('');
        if ($('.vm_select .checkbox:checked').length > 0) {
          $('.vm_select .checkbox:checked').each(function() {
            var vm = $(this).closest('.vm');
            if ($(vm).find('.dst_account_id').text() != '' && $(vm).find('.dst_zone_id').text() !='' &&
                $(vm).find('.dst_compute_offering_id').text() != '') {
              var vm_id = $(vm).data('id');
              var account_display = $(vm).find('.dst_account_id').text();
              var cs_obj = cs_objs['accounts'][account_display];
              vms[vm_id]['cs_account_display'] = account_display;
              vms[vm_id]['cs_account'] = cs_obj['account'];
              vms[vm_id]['cs_domain'] = cs_obj['domain'];
              vms[vm_id]['cs_zone'] = $(vm).find('.dst_zone_id').text();
              vms[vm_id]['cs_zone_display'] = $(vm).find('.dst_zone').text();
              vms[vm_id]['cs_service_offering'] = $(vm).find('.dst_compute_offering_id').text();
              vms[vm_id]['cs_service_offering_display'] = $(vm).find('.dst_compute_offering').text();
              if ($(vm).find('.dst_network_id').text() != '') {
                vms[vm_id]['cs_network'] = $(vm).find('.dst_network_id').text();
                vms[vm_id]['cs_network_display'] = $(vm).find('.dst_network').text();
              }
              migrate.push(vm_id);
            } else {
              ready = false;
              $('#notice').append($(vm).find('h4').text()+' is missing required fields for migration.<br/>');
            }
          });
        } else {
          $('#notice').append('You need to select VMs to migrate...');
          ready = false;
        }
        if (ready) {
          // the vms object has been updated.  save the updated vms object to the server.
          $.ajax({
            url: "/vms/save",
            type: "POST",
            data: {
              "vms":JSON.stringify(vms)
            },
            contentType: "application/json; charset=utf-8",
            success: function(data) {
              $.ajax({
                url: "/migration/start",
                type: "POST",
                data: {
                  "migrate":JSON.stringify(migrate),
                  "timestamp":new Date().getTime()
                },
                contentType: "application/json; charset=utf-8",
                beforeSend: function(xhr, settings) {
                  $('.log_output').addClass('active');
                  $('.log_output').val('... Waiting for initial log data ...');
                  $('#ui-accordion-accordion-panel-0 .overlay').show();
                  $('#accordion').accordion('option', 'active', 1);
                },
                success: function(data) {
                  poll_interval = setInterval('get_migration_log();', 10000);
                  $('#notice').removeClass().html('The migration has started.  View the log for progress...');
                  $('#notice').show();
                  setTimeout(function() {
                    $('#notice').fadeOut();
                  }, 5000);
                },
                error: function(xhr, status, err) {
                  $('.log_output').removeClass('active');
                  $('#notice').removeClass().addClass('error').html('Failed to start the migration process...<br />'+status+': '+err);
                  $('#notice').show();
                  $('#ui-accordion-accordion-panel-0 .overlay').hide();
                  $('#accordion').accordion('option', 'active', 0);
                  setTimeout(function() {
                    $('#notice').fadeOut();
                  }, 5000);
                }
              });
            },
            error: function(xhr, status, err) {
              $('#notice').removeClass().addClass('error').html('Failed to save the configuration to the server...<br />'+status+': '+err);
              $('#notice').show();
              setTimeout(function() {
                $('#notice').fadeOut();
              }, 5000);
            }
          });
        } else {
          $('#notice').removeClass().addClass('error');
          $('#notice').show();
          setTimeout(function() {
            $('#notice').fadeOut();
          }, 5000);
        }
      }

      // poll for log updates
      function get_migration_log() {
        $.ajax({
          url: "/migration/log",
          success: function(data) {
            if (data != '') {
              $('.log_output').val(data);
              $('.log_output').scrollTop($('.log_output')[0].scrollHeight);
              if (ends_with(data, '~~~ ~~~ ~~~ ~~~\n')) {
                refresh_vms();
                refresh_logs();
                clearInterval(poll_interval);
                $('.log_output').removeClass('active');
                $('#ui-accordion-accordion-panel-0 .overlay').hide();
                $('.migrate').removeAttr('disabled');
              }
            }
          },
          error: function(xhr, status, err) {
            $('#notice').removeClass().addClass('error').html('Poll for migration log errored...<br />'+status+': '+err);
            $('#notice').show();
            setTimeout(function() {
              $('#notice').fadeOut();
            }, 5000);
          }
        });
      }

      // refresh the vms list
      function refresh_vms() {
        $.ajax({
          url: "/vms/refresh",
          success: function(data) {
            vms = JSON.parse(data);
            // remove existing vms from list
            $('.vm_list .vm:not(#vm_tpl)').each(function() {
              $(this).remove();
            });
            build_vm_list(); // add the vms again
          }
        });
      }

      // refresh the logs list
      function refresh_logs() {
        $.ajax({
          url: "/logs/refresh",
          success: function(data) {
            $('.recent_logs').html(data);
          }
        });
      }

      // suffix test
      function ends_with(str, suffix) {
        return str.indexOf(suffix, str.length - suffix.length) !== -1;
      }
    </script>
	</head>
	<body>
    <div id="notice" style="display:none;"></div>
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
          <div class="overlay" style="display:none;">
            <div class="overlay_text">
              ... MIGRATING ...<br />
              <a href="javascript:$('#accordion').accordion('option', 'active', 1);">view progress</a>
            </div>
          </div>
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
            
            <div id="vm_tpl" class="vm">
              <h4></h4>
              <span class="vm_state"></span>
              <span class="vm_select">
                <span class="vm_select_label">Select</span>
                <input class="checkbox" type="checkbox" /><label class="checkbox_label"></label>
              </span>
              <div class="vm_content" style="display:none;">
                <div class="left">
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
          <!--<button class="edit_migration">Migration Details</button>-->
          <textarea class="log_output"></textarea>
          <!--<div class="clear button_wrapper">
            <button class="download_log">Download Full Log</button>
          </div>-->
          <div class="recent_logs">{{!log_list}}</div>
        </div>
      </div>
    </div>
  </body>
</html>
            