<?php
/**
 * Add/Edit Show — implements every field in Spec Section 11. Renders three
 * independent connection surfaces below the main show-details form: a
 * standalone Captivate "Connect" form (Section 6.1's own explicit connection
 * action), and a YouTube Connect/Disconnect control (Section 6.3) that's a
 * pair of plain nonce-protected links to admin-post.php rather than a form -
 * each just starts or tears down an OAuth flow, with no extra fields to
 * submit.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Edit_Show_Page {

	public static function render() {
		if ( ! current_user_can( Net_Gain_Admin_Menu::CAPABILITY ) ) {
			wp_die( 'You do not have permission to access this page.' );
		}

		$show_id = isset( $_GET['show_id'] ) ? (int) $_GET['show_id'] : 0;
		$is_new  = 0 === $show_id;
		$show    = $is_new ? null : get_post( $show_id );

		if ( ! $is_new && ! $show ) {
			wp_die( 'Show not found.' );
		}

		$meta = array();
		if ( ! $is_new ) {
			foreach ( Net_Gain_CPT_Show::meta_keys() as $key ) {
				$meta[ $key ] = get_post_meta( $show_id, $key, true );
			}
		}
		$get = function ( $key, $default = '' ) use ( $meta ) {
			return isset( $meta[ $key ] ) && '' !== $meta[ $key ] ? $meta[ $key ] : $default;
		};

		$primary_talent_id = $is_new ? 0 : Net_Gain_Talent_Assignments::get_effective_talent( $show_id, current_time( 'Y-m-d' ) );

		self::render_notices();
		?>
		<div class="wrap ng-edit-show">
			<h1><?php echo $is_new ? 'Add New Show' : 'Edit Show: ' . esc_html( $show->post_title ); ?></h1>

			<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
				<?php wp_nonce_field( 'ng_save_show', 'ng_save_show_nonce' ); ?>
				<input type="hidden" name="action" value="ng_save_show">
				<input type="hidden" name="show_id" value="<?php echo esc_attr( $show_id ); ?>">

				<table class="form-table" role="presentation">

					<tr>
						<th><label for="ng_title">Show name</label></th>
						<td>
							<input type="text" id="ng_title" name="ng_title" class="regular-text" required
								value="<?php echo esc_attr( $show ? $show->post_title : '' ); ?>">
							<p class="description">The show's public name, e.g. "Net Gain Edtech". Displayed on the website, in Captivate, and on YouTube.</p>
						</td>
					</tr>

					<tr>
						<th><label for="ng_vertical_id">Vertical template</label></th>
						<td>
							<?php if ( $is_new ) : ?>
								<select id="ng_vertical_id" name="ng_vertical_id">
									<option value="0">— None (start with blank guidelines) —</option>
									<?php foreach ( self::get_verticals() as $vertical ) : ?>
										<option value="<?php echo esc_attr( $vertical->ID ); ?>"><?php echo esc_html( $vertical->post_title ); ?></option>
									<?php endforeach; ?>
								</select>
								<p class="description">
									Seeds this show's starting editorial guidelines from the chosen template. This choice is <strong>permanent</strong> once saved — guidelines become a normal, independently-editable page from then on.
									<a href="<?php echo esc_url( admin_url( 'post-new.php?post_type=' . Net_Gain_CPT_Vertical::POST_TYPE ) ); ?>" target="_blank" rel="noopener">+ Add New Vertical</a>
								</p>
							<?php else : ?>
								<select disabled>
									<option><?php echo esc_html( $get( 'ng_vertical_id' ) ? get_the_title( $get( 'ng_vertical_id' ) ) : '— None —' ); ?></option>
								</select>
								<input type="hidden" name="ng_vertical_id" value="<?php echo esc_attr( $get( 'ng_vertical_id', 0 ) ); ?>">
								<p class="description">Set at creation; edit the guidelines directly below.</p>
							<?php endif; ?>
						</td>
					</tr>

					<tr>
						<th><label for="ng_slug">Website subdirectory slug</label></th>
						<td>
							<input type="text" id="ng_slug" name="ng_slug" class="regular-text"
								value="<?php echo esc_attr( $show ? $show->post_name : '' ); ?>">
							<p class="description">Appears in the show's URL as <code>netgain.news/shows/<strong>your-slug</strong>/</code>. Lowercase letters, numbers, and hyphens only.</p>
						</td>
					</tr>

					<tr>
						<th>Recording days</th>
						<td>
							<?php
							$days       = array( 'mon' => 'Mon', 'tue' => 'Tue', 'wed' => 'Wed', 'thu' => 'Thu', 'fri' => 'Fri', 'sat' => 'Sat', 'sun' => 'Sun' );
							$rec_days   = $is_new ? array() : (array) $get( 'ng_recording_days', array() );
							foreach ( $days as $key => $label ) :
								?>
								<label style="margin-right:12px;">
									<input type="checkbox" name="ng_recording_days[]" value="<?php echo esc_attr( $key ); ?>" <?php checked( in_array( $key, $rec_days, true ) ); ?>>
									<?php echo esc_html( $label ); ?>
								</label>
							<?php endforeach; ?>
							<p class="description">Days this show's talent records a new episode.</p>
						</td>
					</tr>

					<tr>
						<th><label for="ng_target_time">Target time</label></th>
						<td>
							<input type="time" id="ng_target_time" name="ng_target_time" value="<?php echo esc_attr( $get( 'ng_target_time' ) ); ?>">
							<p class="description">The earliest time the tick loop will request today's script — not a deadline it must be ready by. Actual script availability could be as much as 10 minutes after this time, once the next tick loop pass picks it up.</p>
						</td>
					</tr>

					<tr>
						<th><label for="ng_recording_timezone">Timezone</label></th>
						<td>
							<select id="ng_recording_timezone" name="ng_recording_timezone">
								<?php echo wp_timezone_choice( $get( 'ng_recording_timezone' ) ); ?>
							</select>
							<p class="description">The show's own audience/schedule timezone — deliberately independent of wherever the talent physically lives.</p>
						</td>
					</tr>

					<tr>
						<th>Publish mode</th>
						<td>
							<?php $publish_mode = $get( 'ng_publish_mode', 'immediate' ); ?>
							<label style="display:block;">
								<input type="radio" name="ng_publish_mode" value="immediate" class="ng-publish-mode" <?php checked( 'immediate', $publish_mode ); ?>>
								Immediately once finalized
							</label>
							<label style="display:block;">
								<input type="radio" name="ng_publish_mode" value="scheduled" class="ng-publish-mode" <?php checked( 'scheduled', $publish_mode ); ?>>
								At a scheduled time
							</label>
							<p class="description">Independent of recording time/timezone above — a show can record in one timezone and publish in another.</p>
						</td>
					</tr>

					<tr class="ng-publish-schedule-row" <?php echo 'scheduled' === $publish_mode ? '' : 'style="display:none;"'; ?>>
						<th><label for="ng_publish_time">Publish time</label></th>
						<td>
							<input type="time" id="ng_publish_time" name="ng_publish_time" value="<?php echo esc_attr( $get( 'ng_publish_time' ) ); ?>">
							<select id="ng_publish_timezone" name="ng_publish_timezone">
								<?php echo wp_timezone_choice( $get( 'ng_publish_timezone' ) ); ?>
							</select>
							<p class="description">Used only when publish mode is "At a scheduled time".</p>
						</td>
					</tr>

					<tr>
						<th><label for="ng_lookback_days">Recent-script lookback window (days)</label></th>
						<td>
							<input type="number" id="ng_lookback_days" name="ng_lookback_days" min="1" max="365"
								value="<?php echo esc_attr( $get( 'ng_lookback_days', 30 ) ); ?>">
							<p class="description">How many days of this show's own past <em>reviewed, final</em> scripts are included as context to avoid repeating stories.</p>
						</td>
					</tr>

					<tr>
						<th><label for="ng_primary_talent">Primary talent</label></th>
						<td>
							<?php
							// Administrators are included alongside the ng_talent role - a studio's
							// own proprietor is often also its host, and WordPress's built-in user
							// screen only lets an account hold one role at a time, so requiring a
							// second "Net Gain Talent" role just to appear here would be a needless
							// hurdle for that common case.
							$talent_users = get_users( array( 'role__in' => array( Net_Gain_Roles::TALENT_ROLE, 'administrator' ) ) );
							?>
							<?php if ( empty( $talent_users ) ) : ?>
								<p class="description">No eligible users yet. Create one first: <a href="<?php echo esc_url( admin_url( 'user-new.php' ) ); ?>" target="_blank" rel="noopener">Users → Add New</a>, then set their role to "Net Gain Talent" (or "Administrator").</p>
							<?php else : ?>
								<select id="ng_primary_talent" name="ng_primary_talent">
									<option value="0">— None —</option>
									<?php foreach ( $talent_users as $user ) : ?>
										<option value="<?php echo esc_attr( $user->ID ); ?>" <?php selected( (int) $primary_talent_id, $user->ID ); ?>>
											<?php echo esc_html( $user->display_name ); ?>
										</option>
									<?php endforeach; ?>
								</select>
								<p class="description">The recording talent / website post author / EEAT profile for new episodes. Reassigning this only affects future episodes, never past ones.</p>
							<?php endif; ?>
						</td>
					</tr>

					<tr>
						<th><label for="ng_guidelines_content">Editorial guidelines</label></th>
						<td>
							<?php if ( $is_new ) : ?>
								<p class="description">Created automatically from the selected Vertical template as soon as you save this show.</p>
							<?php elseif ( $get( 'ng_guidelines_page_id' ) ) : ?>
								<?php
								wp_editor(
									get_post_field( 'post_content', $get( 'ng_guidelines_page_id' ) ),
									'ng_guidelines_content',
									array(
										'textarea_name' => 'ng_guidelines_content',
										'textarea_rows' => 25,
										'media_buttons' => false,
										'teeny'         => false,
										'quicktags'     => true,
									)
								);
								?>
								<p class="description">Edit directly here — headings, bold, and lists work via the toolbar above. Saved when you save the show below.</p>
							<?php else : ?>
								<p class="description">No guidelines page found. This shouldn't normally happen — check <code>ng_guidelines_page_id</code> for this show.</p>
							<?php endif; ?>
						</td>
					</tr>

					<tr>
						<th>Branding frames</th>
						<td>
							<?php
							$frames = array(
								'ng_frame_square_id'   => 'Podcast art frame (square, 3000×3000)',
								'ng_frame_16x9_id'     => 'YouTube art frame (16:9)',
								'ng_frame_1200x630_id' => 'Website art frame (1200×630)',
							);
							foreach ( $frames as $meta_key => $label ) :
								$attachment_id = (int) $get( $meta_key, 0 );
								?>
								<div class="ng-frame-picker" style="margin-bottom:16px;">
									<p><strong><?php echo esc_html( $label ); ?></strong></p>
									<div class="ng-frame-preview" style="margin-bottom:6px;">
										<?php if ( $attachment_id ) : ?>
											<?php echo wp_get_attachment_image( $attachment_id, array( 100, 100 ) ); ?>
										<?php endif; ?>
									</div>
									<input type="hidden" class="ng-frame-input" name="<?php echo esc_attr( $meta_key ); ?>" value="<?php echo esc_attr( $attachment_id ); ?>">
									<button type="button" class="button ng-frame-select">Select Image</button>
									<p class="description">PNG with transparency required — this is the compositing cutout each episode's AI-generated art is placed into.</p>
								</div>
							<?php endforeach; ?>
						</td>
					</tr>

					<tr>
						<th>Default fallback images</th>
						<td>
							<?php
							$fallbacks = array(
								'ng_fallback_square_id'   => 'Podcast art fallback (square, 3000×3000, JPEG)',
								'ng_fallback_16x9_id'     => 'YouTube art fallback (1280×720, JPEG)',
								'ng_fallback_1200x630_id' => 'Website art fallback (1200×630, WebP)',
							);
							foreach ( $fallbacks as $meta_key => $label ) :
								$attachment_id = (int) $get( $meta_key, 0 );
								?>
								<div class="ng-frame-picker" style="margin-bottom:16px;">
									<p><strong><?php echo esc_html( $label ); ?></strong></p>
									<div class="ng-frame-preview" style="margin-bottom:6px;">
										<?php if ( $attachment_id ) : ?>
											<?php echo wp_get_attachment_image( $attachment_id, array( 100, 100 ) ); ?>
										<?php endif; ?>
									</div>
									<input type="hidden" class="ng-frame-input" name="<?php echo esc_attr( $meta_key ); ?>" value="<?php echo esc_attr( $attachment_id ); ?>">
									<button type="button" class="button ng-frame-select">Select Image</button>
									<p class="description">A pre-rendered, finished image at this exact spec — used automatically if AI image generation fails for this show. Upload the actual finished JPEG/WebP here, not a frame template.</p>
								</div>
							<?php endforeach; ?>
						</td>
					</tr>

					<tr>
						<th>Image style</th>
						<td>
							<details<?php echo 'duotone' === $get( 'ng_image_style', 'none' ) ? ' open' : ''; ?>>
								<summary style="cursor:pointer;">Image style (optional — default: none)</summary>
								<div style="margin-top:12px;">
									<p>
										<label for="ng_image_style"><strong>Style treatment</strong></label><br>
										<?php $image_style = $get( 'ng_image_style', 'none' ); ?>
										<select id="ng_image_style" name="ng_image_style">
											<option value="none" <?php selected( 'none', $image_style ); ?>>None</option>
											<option value="duotone" <?php selected( 'duotone', $image_style ); ?>>Duotone</option>
										</select>
									</p>
									<?php
									$duotone_colors = array(
										'ng_duotone_shadow_color'    => array( 'Shadow colour', '#000000' ),
										'ng_duotone_highlight_color' => array( 'Highlight colour', '#ffffff' ),
									);
									?>
									<p>
										<?php foreach ( $duotone_colors as $meta_key => $field ) : ?>
											<?php list( $label, $default ) = $field; ?>
											<label for="<?php echo esc_attr( $meta_key ); ?>"><strong><?php echo esc_html( $label ); ?></strong></label>
											<input type="color" class="ng-duotone-picker" value="<?php echo esc_attr( $get( $meta_key, $default ) ); ?>">
											<input type="text" id="<?php echo esc_attr( $meta_key ); ?>" name="<?php echo esc_attr( $meta_key ); ?>" class="ng-duotone-hex" style="width:90px;"
												value="<?php echo esc_attr( $get( $meta_key, $default ) ); ?>" placeholder="<?php echo esc_attr( $default ); ?>">
											&nbsp;&nbsp;
										<?php endforeach; ?>
									</p>
									<p class="description">Type a hex value directly, or use the swatch next to it as a visual picker — not every browser's built-in colour picker shows a hex field on its own.</p>
									<p class="description">Applied to the AI-generated base image before frame compositing: greyscale, then a shadow-colour multiply blend and a highlight-colour screen blend (fixed contrast/brightness/opacity values — only the two colours vary per show). Only used when "Duotone" is selected above.</p>
								</div>
							</details>
						</td>
					</tr>

					<tr>
						<th><label for="ng_status">Show status</label></th>
						<td>
							<?php $status = $get( 'ng_status', 'active' ); ?>
							<select id="ng_status" name="ng_status">
								<option value="active" <?php selected( 'active', $status ); ?>>Active</option>
								<option value="paused" <?php selected( 'paused', $status ); ?>>Paused</option>
								<option value="concluded" <?php selected( 'concluded', $status ); ?>>Concluded</option>
							</select>
							<p class="description">
								<strong>Paused</strong>: automation stops entirely, resumable instantly. <strong>Concluded</strong>: stops new episode production only — published content is never removed or hidden.
							</p>
						</td>
					</tr>

					<tr>
						<th><label for="ng_is_test">Test show</label></th>
						<td>
							<label>
								<input type="checkbox" id="ng_is_test" name="ng_is_test" value="1" <?php checked( (bool) $get( 'ng_is_test', false ) ); ?>>
								This is a test show
							</label>
							<p class="description">Keeps this show collapsed out of the way on the operations dashboard by default (Spec Section 13) — use this for a dedicated test show, never for a real underwriter's show, however small.</p>
						</td>
					</tr>

				</table>

				<?php submit_button( 'Save changes' ); ?>
			</form>

			<?php if ( ! $is_new ) : ?>
				<hr>
				<h2>Connect Captivate show</h2>
				<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
					<?php wp_nonce_field( 'ng_connect_captivate', 'ng_connect_captivate_nonce' ); ?>
					<input type="hidden" name="action" value="ng_connect_captivate">
					<input type="hidden" name="show_id" value="<?php echo esc_attr( $show_id ); ?>">
					<table class="form-table" role="presentation">
						<tr>
							<th><label for="ng_captivate_show_id">Captivate show ID</label></th>
							<td>
								<input type="text" id="ng_captivate_show_id" name="ng_captivate_show_id" class="regular-text"
									value="<?php echo esc_attr( $get( 'ng_captivate_show_id' ) ); ?>">
								<p class="description">The show ID from Captivate's dashboard (shared account login across all shows — only the ID differs per show). Not validated against Captivate live yet; that happens automatically the first time an episode is published to this show.</p>
							</td>
						</tr>
					</table>
					<?php submit_button( 'Connect', 'secondary' ); ?>
				</form>

				<hr>
				<h2>Connect YouTube channel</h2>
				<?php
				$youtube_connected = Net_Gain_Secrets::exists( 'show', $show_id, 'youtube_oauth' );
				$youtube_channel_title = $get( 'ng_youtube_channel_title' );
				$youtube_channel_id    = $get( 'ng_youtube_channel_id' );
				$phone_verified        = $get( 'ng_youtube_phone_verified' );
				?>
				<?php if ( $youtube_connected ) : ?>
					<p>
						Status: <strong>Connected</strong>
						<?php if ( $youtube_channel_title ) : ?>
							— <?php echo esc_html( $youtube_channel_title ); ?> (channel ID <code><?php echo esc_html( $youtube_channel_id ); ?></code>)
						<?php endif; ?>
					</p>
					<?php if ( 'disallowed' === $phone_verified ) : ?>
						<p class="description" style="color:#a00;">
							This channel does not appear to be phone-verified. YouTube requires phone
							verification before a custom thumbnail can be set programmatically, with no
							exception — episodes will still upload, but setting the thumbnail will fail
							until this is resolved in YouTube's own channel settings (Settings → Channel →
							Feature eligibility), then reconnected here.
						</p>
					<?php elseif ( $phone_verified && 'unknown' !== $phone_verified ) : ?>
						<p class="description">Phone verification looks OK (based on YouTube's own "long uploads" eligibility flag — the closest available proxy, not an officially documented verification field).</p>
					<?php endif; ?>
					<a class="button" href="<?php echo esc_url( wp_nonce_url( add_query_arg( array( 'action' => 'ng_disconnect_youtube', 'show_id' => $show_id ), admin_url( 'admin-post.php' ) ), 'ng_disconnect_youtube' ) ); ?>">Disconnect YouTube Channel</a>
				<?php else : ?>
					<p>Status: <strong>Not connected</strong></p>
					<a class="button button-primary" href="<?php echo esc_url( wp_nonce_url( add_query_arg( array( 'action' => 'ng_connect_youtube', 'show_id' => $show_id ), admin_url( 'admin-post.php' ) ), 'ng_connect_youtube' ) ); ?>">Connect YouTube Channel</a>
				<?php endif; ?>
				<p class="description">
					Connecting opts this show into automated YouTube publishing — once connected,
					finalized episodes upload automatically at publish time, the same as Captivate and
					the website above. <strong>Before connecting, make sure this channel is already
					phone-verified</strong> in YouTube's own settings (Settings → Channel → Feature
					eligibility) — YouTube requires this before any custom thumbnail can be set
					programmatically, confirmed with no exception, and there is no way to fix it from
					here after the fact short of reconnecting.
				</p>
			<?php endif; ?>

		</div>
		<?php
	}

	private static function render_notices() {
		if ( isset( $_GET['ng_notice'] ) ) {
			$messages = array(
				'saved'                 => 'Show saved.',
				'captivate_connected'   => 'Captivate show ID saved.',
				'youtube_connected'     => 'YouTube channel connected.',
				'youtube_disconnected'  => 'YouTube channel disconnected.',
				'youtube_connect_failed' => 'Could not connect the YouTube channel — Google rejected or did not complete the connection. Try again; if it keeps failing, this needs a human operator to check the GCP OAuth client configuration.',
			);
			$notice = sanitize_key( wp_unslash( $_GET['ng_notice'] ) );
			if ( isset( $messages[ $notice ] ) ) {
				$css_class = false !== strpos( $notice, 'failed' ) ? 'notice-error' : 'notice-success';
				printf( '<div class="notice %s is-dismissible"><p>%s</p></div>', esc_attr( $css_class ), esc_html( $messages[ $notice ] ) );
			}
		}
	}

	private static function get_verticals() {
		return get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Vertical::POST_TYPE,
				'posts_per_page' => -1,
				'orderby'        => 'title',
				'order'          => 'ASC',
			)
		);
	}

}
