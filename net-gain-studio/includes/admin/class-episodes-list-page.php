<?php

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Episodes_List_Page {

	const SLUG = 'net-gain-episodes';

	public static function render() {
		$show_id = isset( $_GET['show_id'] ) ? (int) $_GET['show_id'] : 0;
		$show    = $show_id ? get_post( $show_id ) : null;

		if ( ! $show || ! Net_Gain_REST_Permissions::can_manage_show( $show_id ) ) {
			wp_die( 'Show not found or you do not have permission to view it.' );
		}

		$episodes = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Episode::POST_TYPE,
				'post_parent'    => $show_id,
				'posts_per_page' => 100,
				'orderby'        => 'date',
				'order'          => 'desc',
			)
		);
		?>
		<div class="wrap">
			<h1>Episodes — <?php echo esc_html( $show->post_title ); ?></h1>

			<?php if ( empty( $episodes ) ) : ?>
				<p>No episodes yet for this show.</p>
			<?php else : ?>
				<table class="wp-list-table widefat fixed striped">
					<thead>
						<tr>
							<th>Date</th>
							<th>Script</th>
							<th>Audio</th>
							<th>Finalization</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						<?php foreach ( $episodes as $episode ) : ?>
							<?php
							$step_status  = get_post_meta( $episode->ID, 'ng_step_status', true ) ?: array();
							$finalization = get_post_meta( $episode->ID, 'ng_finalization', true );
							$finalization = is_array( $finalization ) ? $finalization : array();
							$detail_url   = add_query_arg(
								array( 'page' => Net_Gain_Episode_Detail_Page::SLUG, 'episode_id' => $episode->ID ),
								admin_url( 'admin.php' )
							);
							?>
							<tr>
								<td><?php echo esc_html( get_post_meta( $episode->ID, 'ng_episode_date', true ) ); ?></td>
								<td><?php echo esc_html( $step_status['script_reviewed']['status'] ?? 'pending' ); ?></td>
								<td><?php echo esc_html( $step_status['audio_received']['status'] ?? 'pending' ); ?></td>
								<td><?php echo esc_html( $finalization['state'] ?? 'pending' ); ?></td>
								<td><a href="<?php echo esc_url( $detail_url ); ?>">View</a></td>
							</tr>
						<?php endforeach; ?>
					</tbody>
				</table>
			<?php endif; ?>
		</div>
		<?php
	}
}
