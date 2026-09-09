<?php
/**
 * Operations dashboard (Spec Section 10): one day at a time, rows = Active
 * shows, columns = the 8 pipeline steps. Test shows (Section 13) live in a
 * native <details> disclosure, collapsed by default - the literal "turning
 * triangle" the spec describes, with zero JS. Only Active shows appear in
 * the main grid - a Paused/Concluded show will never produce a new episode,
 * so an endless blank gray row for it every day would just be noise; its
 * history is still reachable via the Episodes list (Phase 4).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Dashboard_Page {

	const SLUG = 'net-gain-studio';

	const COLUMNS = array(
		'script_generated'    => 'Script',
		'script_reviewed'     => 'Reviewed',
		'audio_received'      => 'Audio',
		'metadata_generated'  => 'Metadata',
		'images_rendered'     => 'Images',
		'captivate_published' => 'Captivate',
		'website_published'   => 'Website',
		'youtube_published'   => 'YouTube',
	);

	public static function render() {
		if ( ! current_user_can( Net_Gain_Admin_Menu::CAPABILITY ) ) {
			wp_die( 'You do not have permission to access this page.' );
		}

		$date = self::selected_date();
		?>
		<div class="wrap ng-dashboard">
			<h1><?php echo esc_html( gmdate( 'l, F j, Y', self::to_timestamp( $date ) ) ); ?></h1>
			<p>
				<a class="button" href="<?php echo esc_url( self::date_url( self::shift_date( $date, -1 ) ) ); ?>">&larr; Previous day</a>
				<a class="button" href="<?php echo esc_url( self::date_url( gmdate( 'Y-m-d' ) ) ); ?>">Today</a>
				<a class="button" href="<?php echo esc_url( self::date_url( self::shift_date( $date, 1 ) ) ); ?>">Next day &rarr;</a>
			</p>

			<?php
			$all_shows  = self::get_shows();
			$live_shows = array_filter( $all_shows, fn( $s ) => empty( $s['is_test'] ) );
			$test_shows = array_filter( $all_shows, fn( $s ) => ! empty( $s['is_test'] ) );
			?>

			<?php if ( empty( $live_shows ) ) : ?>
				<p>No active shows yet.</p>
			<?php else : ?>
				<?php self::render_table( $live_shows, $date ); ?>
			<?php endif; ?>

			<?php if ( ! empty( $test_shows ) ) : ?>
				<details class="ng-test-shows">
					<summary>Test shows (<?php echo count( $test_shows ); ?>)</summary>
					<?php self::render_table( $test_shows, $date ); ?>
				</details>
			<?php endif; ?>
		</div>
		<?php
	}

	private static function render_table( $shows, $date ) {
		?>
		<table class="wp-list-table widefat fixed striped ng-dashboard-table">
			<thead>
				<tr>
					<th>Show</th>
					<?php foreach ( self::COLUMNS as $label ) : ?>
						<th><?php echo esc_html( $label ); ?></th>
					<?php endforeach; ?>
				</tr>
			</thead>
			<tbody>
				<?php foreach ( $shows as $show ) : ?>
					<?php self::render_row( $show, $date ); ?>
				<?php endforeach; ?>
			</tbody>
		</table>
		<?php
	}

	private static function render_row( $show, $date ) {
		$episode = self::find_episode_for_date( $show['id'], $date );
		?>
		<tr>
			<td data-label="Show"><strong><?php echo esc_html( $show['name'] ); ?></strong></td>
			<?php foreach ( array_keys( self::COLUMNS ) as $step_key ) : ?>
				<?php self::render_cell( $step_key, $episode, $show ); ?>
			<?php endforeach; ?>
		</tr>
		<?php
	}

	private static function render_cell( $step_key, $episode, $show ) {
		if ( ! $episode ) {
			printf( '<td data-label="%1$s"><span class="ng-led ng-led-pending" title="No episode for this show on this date yet."></span></td>', esc_attr( self::COLUMNS[ $step_key ] ) );
			return;
		}

		$step_status  = $episode['step_status'];
		$finalization = $episode['finalization'];
		$cell_status  = Net_Gain_Dashboard_Status::compute_cell_status( $step_key, $step_status, $finalization, $show );
		$tooltip      = Net_Gain_Dashboard_Status::tooltip( $step_key, $cell_status, $step_status );
		$url          = self::artifact_url( $step_key, $episode );

		$led = sprintf(
			'<span class="ng-led ng-led-%1$s" title="%2$s"></span>',
			esc_attr( $cell_status ),
			esc_attr( $tooltip )
		);

		printf( '<td data-label="%1$s">', esc_attr( self::COLUMNS[ $step_key ] ) );
		if ( $url ) {
			printf( '<a href="%1$s" target="_blank" rel="noopener">%2$s</a>', esc_url( $url ), $led );
		} else {
			echo $led;
		}
		echo '</td>';
	}

	private static function artifact_url( $step_key, $episode ) {
		$review_url = add_query_arg(
			array( 'page' => Net_Gain_Script_Review_Page::SLUG, 'episode_id' => $episode['id'] ),
			admin_url( 'admin.php' )
		);
		$detail_url = add_query_arg(
			array( 'page' => Net_Gain_Episode_Detail_Page::SLUG, 'episode_id' => $episode['id'] ),
			admin_url( 'admin.php' )
		);

		switch ( $step_key ) {
			case 'script_generated':
			case 'script_reviewed':
				return $review_url;
			case 'audio_received':
				return $episode['audio_id'] ? wp_get_attachment_url( $episode['audio_id'] ) : '';
			case 'metadata_generated':
			case 'images_rendered':
				return $detail_url;
			case 'captivate_published':
				return $episode['url_captivate'];
			case 'website_published':
				return $episode['url_website'];
			case 'youtube_published':
				return $episode['url_youtube'];
		}
		return '';
	}

	private static function find_episode_for_date( $show_id, $date ) {
		$posts = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Episode::POST_TYPE,
				'post_parent'    => $show_id,
				'posts_per_page' => 1,
				'meta_key'       => 'ng_episode_date',
				'meta_value'     => $date,
			)
		);
		if ( empty( $posts ) ) {
			return null;
		}

		$post = $posts[0];
		$step_status = get_post_meta( $post->ID, 'ng_step_status', true );
		$finalization = get_post_meta( $post->ID, 'ng_finalization', true );

		return array(
			'id'            => $post->ID,
			'step_status'   => is_array( $step_status ) ? $step_status : Net_Gain_Step_Status::default_status(),
			'finalization'  => is_array( $finalization ) ? $finalization : array(),
			'audio_id'      => (int) get_post_meta( $post->ID, 'ng_audio_attachment_id', true ),
			'url_captivate' => get_post_meta( $post->ID, 'ng_url_captivate', true ),
			'url_website'   => get_post_meta( $post->ID, 'ng_url_website', true ),
			'url_youtube'   => get_post_meta( $post->ID, 'ng_url_youtube', true ),
		);
	}

	private static function get_shows() {
		$posts = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Show::POST_TYPE,
				'posts_per_page' => -1,
				'meta_key'       => 'ng_status',
				'meta_value'     => 'active',
				'orderby'        => 'title',
				'order'          => 'ASC',
			)
		);

		return array_map(
			function ( $post ) {
				return array(
					'id'      => $post->ID,
					'name'    => $post->post_title,
					'is_test' => (bool) get_post_meta( $post->ID, 'ng_is_test', true ),
					'publish_mode' => get_post_meta( $post->ID, 'ng_publish_mode', true ),
				);
			},
			$posts
		);
	}

	private static function selected_date() {
		if ( ! empty( $_GET['ng_date'] ) ) {
			$date = sanitize_text_field( wp_unslash( $_GET['ng_date'] ) );
			if ( preg_match( '/^\d{4}-\d{2}-\d{2}$/', $date ) ) {
				return $date;
			}
		}
		return current_time( 'Y-m-d' );
	}

	private static function shift_date( $date, $days ) {
		return gmdate( 'Y-m-d', self::to_timestamp( $date ) + ( $days * DAY_IN_SECONDS ) );
	}

	/**
	 * Parses a "Y-m-d" string as UTC explicitly, unlike strtotime() (which uses
	 * PHP's configured local timezone to parse a bare date string) combined with
	 * gmdate() (always UTC) - that mismatch can silently shift the displayed date
	 * by a day depending on server timezone config. Spec Section 1: never assume.
	 */
	private static function to_timestamp( $date ) {
		list( $year, $month, $day ) = array_map( 'intval', explode( '-', $date ) );
		return gmmktime( 0, 0, 0, $month, $day, $year );
	}

	private static function date_url( $date ) {
		return add_query_arg( array( 'page' => self::SLUG, 'ng_date' => $date ), admin_url( 'admin.php' ) );
	}
}
