<?php
/**
 * Photos screen (Net Gain Studio > Photos): the per-show photo library's admin UI. The page is a thin shell - the
 * uploader, grid, tag editor and runway meter are built by assets/photos.js against the REST routes in
 * class-rest-photos.php - so everything the operator does here goes through the same permission checks the pipeline uses.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Photos_Page {

	const SLUG = 'net-gain-photos';

	public static function render() {
		if ( ! current_user_can( Net_Gain_Admin_Menu::CAPABILITY ) ) {
			wp_die( 'You do not have permission to access this page.' );
		}

		$shows = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Show::POST_TYPE,
				'post_status'    => 'publish',
				'posts_per_page' => 100,
				'orderby'        => 'title',
				'order'          => 'ASC',
			)
		);

		if ( empty( $shows ) ) {
			echo '<div class="wrap"><h1>Photos</h1><p>Create a show first.</p></div>';
			return;
		}

		$selected = isset( $_GET['show'] ) ? (int) $_GET['show'] : (int) $shows[0]->ID; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
		$show     = null;
		foreach ( $shows as $candidate ) {
			if ( (int) $candidate->ID === $selected ) {
				$show = $candidate;
			}
		}
		$show = $show ?: $shows[0];
		$mode = get_post_meta( $show->ID, 'ng_image_mode', true );
		?>
		<div class="wrap ng-photos" id="ng-photos" data-show="<?php echo esc_attr( $show->ID ); ?>">
			<h1>Photos</h1>

			<?php if ( count( $shows ) > 1 ) : ?>
				<form method="get" style="margin:0 0 12px">
					<input type="hidden" name="page" value="<?php echo esc_attr( self::SLUG ); ?>">
					<label for="ng-photos-show"><strong>Show</strong></label>
					<select id="ng-photos-show" name="show" onchange="this.form.submit()">
						<?php foreach ( $shows as $s ) : ?>
							<option value="<?php echo esc_attr( $s->ID ); ?>" <?php selected( $s->ID, $show->ID ); ?>><?php echo esc_html( $s->post_title ); ?></option>
						<?php endforeach; ?>
					</select>
				</form>
			<?php endif; ?>

			<p class="description" style="max-width:760px">
				Real photographs for <strong><?php echo esc_html( $show->post_title ); ?></strong>'s episode graphics. Drop photos here; each one is
				tagged automatically within a few minutes, then used with a different crop and the show's duotone, and rested for
				<?php echo (int) Net_Gain_Photo_Library::cooldown_days( $show->ID ); ?> days between uses. Originals are kept private.
				<?php if ( 'photos' !== $mode ) : ?>
					<br><strong>Graphics source is currently "<?php echo esc_html( $mode ?: 'ai' ); ?>"</strong> - switch it to "Real photos" in
					<a href="<?php echo esc_url( admin_url( 'admin.php?page=' . Net_Gain_Admin_Menu::EDIT_SLUG . '&show=' . (int) $show->ID ) ); ?>">Edit Show</a>
					when the library is ready.
				<?php endif; ?>
			</p>

			<div id="ng-photos-meter" class="ng-photos-meter" aria-live="polite"></div>

			<div id="ng-photos-drop" class="ng-photos-drop" tabindex="0">
				<strong>Drag photos here</strong> or <a href="#" id="ng-photos-browse">choose files</a>
				<div class="description">JPEG, PNG or WebP, photos only. Best at 4000&times;2700 px or larger. Several at once is fine.</div>
				<input type="file" id="ng-photos-input" multiple accept="image/jpeg,image/png,image/webp" style="display:none">
			</div>
			<div id="ng-photos-uploads" class="ng-photos-uploads"></div>

			<div class="ng-photos-toolbar">
				<span id="ng-photos-filters"></span>
				<input type="search" id="ng-photos-search" placeholder="Search tags or descriptions" style="min-width:240px">
			</div>
			<div id="ng-photos-grid" class="ng-photos-grid"></div>
			<div id="ng-photos-modal" class="ng-photos-modal" hidden></div>
		</div>
		<?php
	}

	public static function enqueue() {
		wp_enqueue_script( 'ng-photos', plugins_url( 'assets/photos.js', NET_GAIN_PLUGIN_FILE ), array(), NET_GAIN_VERSION, true );
		wp_localize_script(
			'ng-photos',
			'ngPhotos',
			array(
				'restUrl' => esc_url_raw( rest_url( 'net-gain/v1' ) ),
				'nonce'   => wp_create_nonce( 'wp_rest' ),
				'topics'  => Net_Gain_Photo_Library::TOPICS,
				'people'  => Net_Gain_Photo_Library::PEOPLE,
			)
		);
	}
}
